from datetime import date, timedelta

from sqlalchemy import select, text

from models import (
    Member,
    MembershipPlan,
    MembershipPurchase,
    MembershipRenewal,
    MembershipSubscription,
    db,
)


DEFAULT_PLANS = (
    {
        "code": "punch_10",
        "name": "10-Class Punch Card",
        "price_cents": 25000,
        "credits": 10,
        "validity_days": 90,
    },
    {
        "code": "monthly_30",
        "name": "Monthly Pass",
        "price_cents": 32000,
        "credits": 30,
        "validity_days": 30,
    },
)


class MembershipPurchaseError(ValueError):
    pass


def ensure_default_plans() -> None:
    for values in DEFAULT_PLANS:
        if db.session.get(MembershipPlan, values["code"]) is None:
            db.session.add(MembershipPlan(**values))
    db.session.commit()


def purchase_membership(
    member_id: int, plan_code: str, processed_by_user_id: int
) -> int:
    """Apply a demo purchase and renewal as one local SQLite transaction."""

    db.session.rollback()
    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        member = db.session.get(Member, member_id)
        plan = db.session.get(MembershipPlan, plan_code)
        if member is None:
            raise MembershipPurchaseError("Member was not found.")
        if plan is None or not plan.is_active:
            raise MembershipPurchaseError("Membership plan is unavailable.")

        today = date.today()
        previous_expiry = member.membership_expires_on
        renewal_start = max(today, previous_expiry)
        new_expiry = renewal_start + timedelta(days=plan.validity_days)

        member.membership_expires_on = new_expiry
        member.credit_balance += plan.credits
        member.status = "active"

        if member.subscription is None:
            member.subscription = MembershipSubscription(
                plan=plan,
                status="active",
                starts_on=today,
                ends_on=new_expiry,
            )
        else:
            member.subscription.plan = plan
            member.subscription.status = "active"
            member.subscription.starts_on = today
            member.subscription.ends_on = new_expiry

        purchase = MembershipPurchase(
            member=member,
            plan=plan,
            amount_paid_cents=plan.price_cents,
            receipt_status="pending",
        )
        renewal = MembershipRenewal(
            member=member,
            processed_by_user_id=processed_by_user_id,
            previous_expiry=previous_expiry,
            new_expiry=new_expiry,
            credits_added=plan.credits,
            notes=f"Demo checkout: {plan.name}",
        )
        db.session.add_all([purchase, renewal])
        db.session.commit()
        return purchase.id
    except Exception:
        db.session.rollback()
        raise


def set_subscription_status(member_id: int, status: str) -> None:
    if status not in {"active", "suspended", "cancelled"}:
        raise ValueError("Invalid subscription status.")

    member = db.get_or_404(Member, member_id)
    if member.subscription is None:
        latest_plan = db.session.scalar(
            select(MembershipPlan).where(MembershipPlan.is_active.is_(True)).limit(1)
        )
        if latest_plan is None:
            raise MembershipPurchaseError("No membership plan is configured.")
        member.subscription = MembershipSubscription(
            plan=latest_plan,
            status=status,
            starts_on=date.today(),
            ends_on=member.membership_expires_on,
        )
    else:
        member.subscription.status = status

    member.status = "active" if status == "active" else "inactive"
    db.session.commit()
