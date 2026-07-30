from .db import db
from .user import utc_now


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('booked', 'cancelled')", name="valid_booking_status"
        ),
        db.CheckConstraint(
            "(NOT credit_refunded) OR "
            "(status = 'cancelled' AND credit_consumed)",
            name="valid_booking_refund_state",
        ),
        db.UniqueConstraint(
            "member_id", "workout_session_id", name="one_booking_per_member_session"
        ),
        db.Index(
            "ix_bookings_workout_session_status", "workout_session_id", "status"
        ),
        db.Index("ix_bookings_member_status", "member_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workout_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default="booked")
    credit_consumed = db.Column(db.Boolean, nullable=False, default=True)
    credit_refunded = db.Column(db.Boolean, nullable=False, default=False)
    booked_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    cancelled_at = db.Column(db.DateTime(timezone=True))

    member = db.relationship("Member", back_populates="bookings")
    workout_session = db.relationship("WorkoutSession", back_populates="bookings")

    def __repr__(self) -> str:
        return (
            f"<Booking member_id={self.member_id} "
            f"workout_session_id={self.workout_session_id} status={self.status!r}>"
        )
