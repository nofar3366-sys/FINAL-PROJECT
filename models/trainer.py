from .db import db
from .user import utc_now


class Trainer(db.Model):
    __tablename__ = "trainers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    first_name = db.Column(
        db.String(80), nullable=False, default="", server_default=""
    )
    last_name = db.Column(
        db.String(80), nullable=False, default="", server_default=""
    )
    specialty = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255), unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = db.relationship("User", back_populates="trainer")
    workout_sessions = db.relationship("WorkoutSession", back_populates="trainer")

    @property
    def full_name(self) -> str:
        """Unbreakable display name for Jinja (never raises)."""

        try:
            return f"{self.first_name or ''} {self.last_name or ''}".strip() or "Trainer"
        except Exception:
            return "Trainer"


    def __repr__(self) -> str:
        return f"<Trainer {self.full_name!r} specialty={self.specialty!r}>"
