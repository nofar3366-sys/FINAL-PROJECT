from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .db import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('manager', 'member', 'trainer')", name="valid_user_role"
        ),
        db.CheckConstraint("is_active IN (0, 1)", name="valid_user_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    member = db.relationship(
        "Member", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    trainer = db.relationship(
        "Trainer", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    processed_renewals = db.relationship(
        "MembershipRenewal", back_populates="processed_by"
    )
    audit_logs = db.relationship("AuditLog", back_populates="actor")

    def set_password(self, password: str) -> None:
        if not password:
            raise ValueError("Password is required.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role!r}>"
