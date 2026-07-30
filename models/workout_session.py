from datetime import datetime, timedelta

from .db import db
from .user import utc_now


class WorkoutSession(db.Model):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        db.CheckConstraint(
            "duration_minutes > 0", name="positive_session_duration"
        ),
        db.CheckConstraint("max_capacity > 0", name="positive_session_capacity"),
        db.CheckConstraint(
            "status IN ('scheduled', 'cancelled', 'completed')",
            name="valid_session_status",
        ),
        db.Index("ix_workout_sessions_status_starts_at", "status", "starts_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(
        db.Integer,
        db.ForeignKey("trainers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(150), nullable=False)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    max_capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="scheduled")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    trainer = db.relationship("Trainer", back_populates="workout_sessions")
    bookings = db.relationship("Booking", back_populates="workout_session")

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def active_booking_count(self) -> int:
        return sum(booking.status == "booked" for booking in self.bookings)

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.max_capacity - self.active_booking_count)

    def __repr__(self) -> str:
        return f"<WorkoutSession {self.title!r} starts_at={self.starts_at!r}>"
