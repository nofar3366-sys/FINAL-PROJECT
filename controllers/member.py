from datetime import date, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from controllers.auth import clear_invalid_session, member_required, validate_csrf
from controllers.safe_db import recover_from_db_error
from models import MembershipPlan, db
from services.booking_service import BookingError, book_session, cancel_booking
from services.member_service import (
    MemberServiceError,
    answer_schedule_question,
    build_dashboard_context,
    build_schedule_context,
    finalize_purchase_receipt,
    recommend_workout,
)
from services.membership_service import MembershipPurchaseError, purchase_membership
from skills.availability import get_class_availability_skill

member_bp = Blueprint("member", __name__, url_prefix="/member")


@member_bp.get("/dashboard")
@member_required
def dashboard():
    try:
        member = getattr(g.user, "member", None)
        if member is None:
            clear_invalid_session(
                "Your member profile is missing. Please sign in again."
            )
            return redirect(url_for("auth.login"))
        context, query_failed = build_dashboard_context(member)
        if query_failed:
            current_app.logger.error("Member dashboard booking query failed")
            flash(
                "Some workout details could not be loaded. You can still use the "
                "rest of your dashboard.",
                "warning",
            )
        return render_template("member/dashboard.html", **context)
    except Exception as exc:
        current_app.logger.exception("Member dashboard failed: %s", exc)
        flash(
            "We could not open your dashboard just now. Your session is still active.",
            "warning",
        )
        return redirect(url_for("member.schedule"))


@member_bp.get("/schedule")
@member_required
def schedule():
    member = g.user.member
    try:
        context = build_schedule_context(member)
    except SQLAlchemyError:
        current_app.logger.exception("Member schedule query failed")
        recover_from_db_error()
        return redirect(url_for("auth.login"))
    return render_template("member/schedule.html", **context)


@member_bp.get("/renewal")
@member_required
def renewal():
    member = g.user.member
    plans = db.session.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.price_cents)
    ).all()
    return render_template("member/renewal.html", member=member, plans=plans)


@member_bp.post("/sessions/<int:session_id>/book")
@member_required
def book(session_id: int):
    validate_csrf()
    member = g.user.member
    try:
        book_session(member.id, session_id)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Booking confirmed. One credit was used.", "success")
    return redirect(url_for("member.schedule"))


@member_bp.post("/bookings/<int:booking_id>/cancel")
@member_required
def cancel(booking_id: int):
    validate_csrf()
    member = g.user.member
    try:
        cancel_booking(member.id, booking_id)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Booking cancelled. One credit was refunded.", "success")
    return redirect(url_for("member.schedule"))


@member_bp.post("/membership/purchase")
@member_required
def purchase():
    validate_csrf()
    member = g.user.member
    plan_code = request.form.get("plan_code", "")
    try:
        purchase_id = purchase_membership(member.id, plan_code, g.user.id)
    except MembershipPurchaseError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("member.renewal"))

    try:
        receipt_status = finalize_purchase_receipt(
            purchase_id,
            member,
            current_app.extensions["receipt_email"],
        )
    except MemberServiceError:
        current_app.logger.error(
            "Committed purchase %s could not be reloaded", purchase_id
        )
        flash(
            "Purchase completed, but the receipt record could not be loaded.",
            "warning",
        )
        return redirect(url_for("member.renewal"))
    except Exception:
        # The membership purchase is already durable. Receipt bookkeeping must
        # never roll it back or log the member out.
        db.session.rollback()
        current_app.logger.exception(
            "Purchase %s succeeded but receipt finalization failed", purchase_id
        )
        flash(
            "Purchase completed, but the receipt will need to be retried.",
            "warning",
        )
        return redirect(url_for("member.renewal"))

    if receipt_status == "failed":
        flash("Purchase completed, but the email receipt could not be sent.", "warning")
    else:
        flash("Demo purchase completed and receipt processed.", "success")
    return redirect(url_for("member.renewal"))


@member_bp.route("/assistant", methods=("GET", "POST"))
@member_required
def assistant():
    member = g.user.member
    if request.method == "GET":
        return render_template(
            "member/ai_assistant.html",
            member=member,
            ai_answer=None,
            skill_executed=False,
            suggested_date=(date.today() + timedelta(days=1)).isoformat(),
        )

    validate_csrf()
    question = request.form.get("question", "").strip()
    try:
        answer = answer_schedule_question(
            question,
            current_app.extensions["ai_service"],
        )
    except Exception as exc:
        # Query construction, Groq timeouts, malformed responses, and optional
        # service failures all degrade to HTTP 200 without touching auth state.
        db.session.rollback()
        current_app.logger.error(
            "Member AI chat failed: %s", exc, exc_info=True
        )
        answer = (
            "The studio assistant is temporarily unavailable. "
            "Your session is still active; please try again shortly."
        )
    return render_template(
        "member/ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=False,
        suggested_date=(date.today() + timedelta(days=1)).isoformat(),
    )


@member_bp.post("/assistant/availability")
@member_required
def assistant_availability():
    validate_csrf()
    member = g.user.member
    try:
        result = get_class_availability_skill(
            request.form.get("date", ""),
            request.form.get("specialty", ""),
        )
        classes = result["classes"]
        if classes:
            answer = "\n".join(
                f"{item['title']} with {item['trainer']} at "
                f"{item['starts_at'][11:16]} — {item['remaining_capacity']} spots"
                for item in classes
            )
        else:
            answer = (
                f"No {result['specialty']} classes are scheduled on {result['date']}."
            )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            "Member availability assistant failed: %s", exc, exc_info=True
        )
        answer = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Availability is temporarily unavailable. Please try again."
        )
    return render_template(
        "member/ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=True,
        suggested_date=request.form.get("date", ""),
    )


@member_bp.post("/assistant/recommend")
@member_required
def assistant_recommendation():
    validate_csrf()
    member = g.user.member
    goal = request.form.get("goal", "").strip()
    try:
        answer = recommend_workout(
            member,
            goal,
            current_app.extensions["ai_service"],
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            "Member AI recommendation failed: %s", exc, exc_info=True
        )
        answer = (
            "Workout recommendations are temporarily unavailable. "
            "Your session is still active; please try again shortly."
        )
    return render_template(
        "member/ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=False,
        recommendation_executed=True,
        suggested_date=(date.today() + timedelta(days=1)).isoformat(),
        goal=goal,
    )
