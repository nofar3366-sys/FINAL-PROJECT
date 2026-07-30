from .db import db
from .user import utc_now


class MembershipPlan(db.Model):
    __tablename__ = "membership_plans"
    __table_args__ = (
        db.CheckConstraint("price_cents >= 0", name="nonnegative_plan_price"),
        db.CheckConstraint("credits > 0", name="positive_plan_credits"),
        db.CheckConstraint("validity_days > 0", name="positive_plan_validity"),
    )

    code = db.Column(db.String(40), primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    price_cents = db.Column(db.Integer, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    validity_days = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    purchases = db.relationship("MembershipPurchase", back_populates="plan")
    subscriptions = db.relationship("MembershipSubscription", back_populates="plan")


class MembershipPurchase(db.Model):
    __tablename__ = "membership_purchases"
    __table_args__ = (
        db.CheckConstraint(
            "amount_paid_cents >= 0", name="nonnegative_purchase_amount"
        ),
        db.CheckConstraint(
            "receipt_status IN ('pending', 'sent', 'mocked', 'failed')",
            name="valid_receipt_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_code = db.Column(
        db.String(40),
        db.ForeignKey("membership_plans.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_paid_cents = db.Column(db.Integer, nullable=False)
    receipt_status = db.Column(db.String(20), nullable=False, default="pending")
    receipt_reference = db.Column(db.String(255))
    purchased_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    member = db.relationship("Member", back_populates="purchases")
    plan = db.relationship("MembershipPlan", back_populates="purchases")


class MembershipSubscription(db.Model):
    __tablename__ = "membership_subscriptions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'suspended', 'cancelled')",
            name="valid_subscription_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    plan_code = db.Column(
        db.String(40),
        db.ForeignKey("membership_plans.code", ondelete="RESTRICT"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default="active")
    starts_on = db.Column(db.Date, nullable=False)
    ends_on = db.Column(db.Date, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    member = db.relationship("Member", back_populates="subscription")
    plan = db.relationship("MembershipPlan", back_populates="subscriptions")
