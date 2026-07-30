from datetime import datetime, timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from controllers.auth import trainer_required, validate_csrf
from models import Booking, WorkoutSession, db
from models.time_utils import ensure_utc, utc_now
from services.scheduling_service import SchedulingError, cancel_session, create_session


trainer_bp = Blueprint("trainer", __name__, url_prefix="/trainer")


@trainer_bp.get("/dashboard")
@trainer_required
def dashboard():
    sessions = db.session.scalars(
        select(WorkoutSession)
        .where(WorkoutSession.trainer_id == g.user.trainer.id)
        .order_by(WorkoutSession.starts_at)
    ).all()
    return render_template(
        "trainer_dashboard.html",
        trainer=g.user.trainer,
        sessions=sessions,
    )


@trainer_bp.route("/sessions/new", methods=("GET", "POST"))
@trainer_required
def new_session():
    if request.method == "POST":
        validate_csrf()
        try:
            create_session(
                trainer_id=g.user.trainer.id,
                title=request.form.get("title", ""),
                starts_at=ensure_utc(
                    datetime.fromisoformat(request.form.get("starts_at", ""))
                ),
                duration_minutes=int(request.form.get("duration_minutes", "60")),
                max_capacity=int(request.form.get("max_capacity", "0")),
            )
        except (ValueError, SchedulingError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Workout added to the weekly schedule.", "success")
            return redirect(url_for("trainer.dashboard"))

    return render_template(
        "trainer_session_form.html",
        trainer=g.user.trainer,
        suggested_start=(utc_now() + timedelta(days=1))
        .replace(minute=0, second=0, microsecond=0)
        .isoformat(timespec="minutes"),
    )


@trainer_bp.post("/sessions/<int:session_id>/cancel")
@trainer_required
def cancel_workout_session(session_id: int):
    validate_csrf()
    workout_session = db.get_or_404(WorkoutSession, session_id)
    if workout_session.trainer_id != g.user.trainer.id:
        return "", 403
    try:
        cancel_session(session_id)
    except SchedulingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Training slot cancelled and booked credits refunded.", "success")
    return redirect(url_for("trainer.dashboard"))


@trainer_bp.get("/sessions/<int:session_id>/participants")
@trainer_required
def participants(session_id: int):
    workout_session = db.get_or_404(WorkoutSession, session_id)
    if workout_session.trainer_id != g.user.trainer.id:
        return "", 403
    bookings = db.session.scalars(
        select(Booking)
        .where(
            Booking.workout_session_id == session_id,
            Booking.status == "booked",
        )
        .order_by(Booking.booked_at)
    ).all()
    return render_template(
        "trainer_participants.html",
        trainer=g.user.trainer,
        workout_session=workout_session,
        bookings=bookings,
    )
