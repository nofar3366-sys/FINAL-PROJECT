from datetime import date, datetime

from sqlalchemy import func, select, text

from models import Booking, Member, WorkoutSession, db


class BookingError(ValueError):
    pass


def book_session(member_id: int, workout_session_id: int) -> None:
    """Book one place and consume one credit under an immediate SQLite lock."""

    db.session.rollback()
    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        member = db.session.get(Member, member_id)
        workout_session = db.session.get(WorkoutSession, workout_session_id)
        if member is None or workout_session is None:
            raise BookingError("Member or session was not found.")
        if not member.has_active_membership(date.today()):
            raise BookingError("Your membership is inactive or expired.")
        if member.credit_balance <= 0:
            raise BookingError("You do not have enough credits.")
        if workout_session.status != "scheduled":
            raise BookingError("This session is not available.")
        if workout_session.starts_at <= datetime.now():
            raise BookingError("This session has already started.")

        existing = db.session.scalar(
            select(Booking.id).where(
                Booking.member_id == member_id,
                Booking.workout_session_id == workout_session_id,
            )
        )
        if existing:
            raise BookingError("You already have a booking record for this session.")

        active_count = db.session.scalar(
            select(func.count(Booking.id)).where(
                Booking.workout_session_id == workout_session_id,
                Booking.status == "booked",
            )
        )
        if int(active_count or 0) >= workout_session.max_capacity:
            raise BookingError("This session is full.")

        db.session.add(
            Booking(
                member_id=member_id,
                workout_session_id=workout_session_id,
                status="booked",
                credit_consumed=True,
                credit_refunded=False,
            )
        )
        member.credit_balance -= 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def cancel_booking(member_id: int, booking_id: int) -> None:
    """Cancel a future booking and restore its credit exactly once."""

    db.session.rollback()
    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        booking = db.session.get(Booking, booking_id)
        if booking is None or booking.member_id != member_id:
            raise BookingError("Booking was not found.")
        if booking.status != "booked":
            raise BookingError("This booking is already cancelled.")
        if booking.workout_session.starts_at <= datetime.now():
            raise BookingError("Started sessions cannot be cancelled.")

        booking.status = "cancelled"
        booking.cancelled_at = datetime.now()
        if booking.credit_consumed and not booking.credit_refunded:
            booking.member.credit_balance += 1
            booking.credit_refunded = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
