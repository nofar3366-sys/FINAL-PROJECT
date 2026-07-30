from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, select

from controllers.auth import login_required, validate_csrf
from models import Booking, MembershipPlan, MembershipPurchase, WorkoutSession, db
from services.ai_service import AIServiceError, KnowledgeDocument
from services.booking_service import BookingError, book_session, cancel_booking
from services.membership_service import MembershipPurchaseError, purchase_membership
from skills.availability import get_class_availability_skill

member_bp = Blueprint("member", __name__, url_prefix="/member")
WEEK_DAYS = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


@member_bp.get("/dashboard")
@login_required
def dashboard():
    member = _current_member()
    upcoming_bookings = db.session.scalars(
        select(Booking)
        .join(Booking.workout_session)
        .where(
            Booking.member_id == member.id,
            Booking.status == "booked",
            WorkoutSession.starts_at > datetime.now(),
        )
        .order_by(WorkoutSession.starts_at)
    ).all()
    used_credits = db.session.scalar(
        select(func.count(Booking.id)).where(
            Booking.member_id == member.id,
            Booking.status == "booked",
            Booking.credit_consumed.is_(True),
            Booking.credit_refunded.is_(False),
        )
    )
    return render_template(
        "dashboard.html",
        member=member,
        upcoming_bookings=upcoming_bookings,
        used_credits=int(used_credits or 0),
    )


@member_bp.get("/schedule")
@login_required
def schedule():
    member = _current_member()
    sessions, bookings, booked_session_ids = _schedule_data(member.id)
    workouts_by_day = {day: [] for day in WEEK_DAYS}
    for workout_session in sessions:
        day_index = (workout_session.starts_at.weekday() + 1) % 7
        workout_type = _workout_type(
            workout_session.title, workout_session.trainer.specialty
        )
        workouts_by_day[WEEK_DAYS[day_index]].append(
            {
                "id": workout_session.id,
                "time": workout_session.starts_at.strftime("%H:%M"),
                "date": workout_session.starts_at.strftime("%d %b"),
                "title": workout_session.title,
                "trainer": workout_session.trainer.full_name,
                "specialty": workout_session.trainer.specialty,
                "type": workout_type,
                "type_label": workout_type.title(),
                "status": workout_session.status,
                "remaining_capacity": workout_session.remaining_capacity,
                "duration_minutes": workout_session.duration_minutes,
                "is_booked": workout_session.id in booked_session_ids,
            }
        )
    return render_template(
        "schedule.html",
        member=member,
        bookings=bookings,
        week_days=WEEK_DAYS,
        workouts_by_day=workouts_by_day,
    )


@member_bp.get("/renewal")
@login_required
def renewal():
    member = _current_member()
    plans = db.session.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.price_cents)
    ).all()
    return render_template("renewal.html", member=member, plans=plans)


@member_bp.post("/sessions/<int:session_id>/book")
@login_required
def book(session_id: int):
    validate_csrf()
    member = _current_member()
    try:
        book_session(member.id, session_id)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Booking confirmed. One credit was used.", "success")
    return redirect(url_for("member.schedule"))


@member_bp.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel(booking_id: int):
    validate_csrf()
    member = _current_member()
    try:
        cancel_booking(member.id, booking_id)
    except BookingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Booking cancelled. One credit was refunded.", "success")
    return redirect(url_for("member.schedule"))


@member_bp.post("/membership/purchase")
@login_required
def purchase():
    validate_csrf()
    member = _current_member()
    plan_code = request.form.get("plan_code", "")
    try:
        purchase_id = purchase_membership(member.id, plan_code, g.user.id)
    except MembershipPurchaseError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("member.renewal"))

    purchase_record = db.session.get(MembershipPurchase, purchase_id)
    result = current_app.extensions["receipt_email"].send_receipt(
        to_email=member.user.email,
        member_name=member.full_name,
        plan_name=purchase_record.plan.name,
        amount_cents=purchase_record.amount_paid_cents,
        credits=purchase_record.plan.credits,
        expires_on=member.membership_expires_on.isoformat(),
    )
    purchase_record.receipt_status = result.status
    purchase_record.receipt_reference = result.reference
    db.session.commit()

    if result.status == "failed":
        flash("Purchase completed, but the email receipt could not be sent.", "warning")
    else:
        flash("Demo purchase completed and receipt processed.", "success")
    return redirect(url_for("member.renewal"))


@member_bp.route("/assistant", methods=("GET", "POST"))
@login_required
def assistant():
    member = _current_member()
    if request.method == "GET":
        return render_template(
            "ai_assistant.html",
            member=member,
            ai_answer=None,
            skill_executed=False,
            suggested_date=(date.today() + timedelta(days=1)).isoformat(),
        )

    validate_csrf()
    question = request.form.get("question", "").strip()
    sessions = db.session.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.starts_at > datetime.now(),
        )
        .order_by(WorkoutSession.starts_at)
        .limit(12)
    ).all()
    schedule_text = "\n".join(
        f"{item.title} with {item.trainer.full_name} on "
        f"{item.starts_at:%Y-%m-%d at %H:%M}; "
        f"{item.remaining_capacity} places remaining."
        for item in sessions
    )
    documents = (
        KnowledgeDocument(
            key="live-schedule",
            title="Current training schedule",
            content=schedule_text or "No upcoming sessions are scheduled.",
        ),
    )
    try:
        answer = current_app.extensions["ai_service"].ask(question, documents)
    except (ValueError, AIServiceError) as exc:
        answer = f"Demo assistant response: {exc}"
    return render_template(
        "ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=False,
        suggested_date=(date.today() + timedelta(days=1)).isoformat(),
    )


@member_bp.post("/assistant/availability")
@login_required
def assistant_availability():
    validate_csrf()
    member = _current_member()
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
    except ValueError as exc:
        answer = str(exc)
    return render_template(
        "ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=True,
        suggested_date=request.form.get("date", ""),
    )


@member_bp.post("/assistant/recommend")
@login_required
def assistant_recommendation():
    validate_csrf()
    member = _current_member()
    goal = request.form.get("goal", "").strip()
    upcoming = db.session.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.status == "scheduled",
            WorkoutSession.starts_at > datetime.now(),
        )
        .order_by(WorkoutSession.starts_at)
        .limit(20)
    ).all()
    available_classes = [
        {
            "title": item.title,
            "specialty": item.trainer.specialty,
            "starts_at": item.starts_at.strftime("%A, %d %B at %H:%M"),
            "remaining_capacity": item.remaining_capacity,
        }
        for item in upcoming
        if item.remaining_capacity > 0
    ]
    recent_workouts = [
        booking.workout_session.title
        for booking in sorted(member.bookings, key=lambda item: item.booked_at, reverse=True)
        if booking.status == "booked"
    ][:3]
    try:
        answer = current_app.extensions["ai_service"].recommend_workout(
            goal,
            {
                "name": member.full_name,
                "credits": member.credit_balance,
                "membership_active": member.has_active_membership(),
                "recent_workouts": ", ".join(recent_workouts),
            },
            available_classes,
        )
    except (ValueError, AIServiceError) as exc:
        answer = f"Recommendation unavailable: {exc}"
    return render_template(
        "ai_assistant.html",
        member=member,
        ai_answer=answer,
        skill_executed=False,
        recommendation_executed=True,
        suggested_date=(date.today() + timedelta(days=1)).isoformat(),
        goal=goal,
    )


def _current_member():
    if g.user.role != "member" or g.user.member is None:
        abort(403)
    return g.user.member


def _schedule_data(member_id: int):
    sessions = db.session.scalars(
        select(WorkoutSession)
        .where(
            WorkoutSession.status == "scheduled",
            WorkoutSession.starts_at > datetime.now(),
        )
        .order_by(WorkoutSession.starts_at)
    ).all()
    bookings = db.session.scalars(
        select(Booking)
        .where(Booking.member_id == member_id)
        .order_by(Booking.booked_at.desc())
    ).all()
    booked_session_ids = {
        booking.workout_session_id
        for booking in bookings
        if booking.status == "booked"
    }
    return sessions, bookings, booked_session_ids


def _workout_type(title: str, specialty: str) -> str:
    """Map studio terminology to a small set of calendar accent classes."""

    value = f"{title} {specialty}".lower()
    if "strength" in value or "functional" in value:
        return "strength"
    if "cardio" in value or "hiit" in value:
        return "cardio"
    if "pilates" in value:
        return "pilates"
    if "yoga" in value or "mobility" in value:
        return "yoga"
    return "general"
