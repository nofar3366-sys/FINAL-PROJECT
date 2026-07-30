import hmac

from werkzeug.security import check_password_hash, generate_password_hash

from .db import db
from .time_utils import utc_now

__all__ = ["User", "utc_now"]


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('manager', 'member', 'trainer')", name="valid_user_role"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    # Text avoids truncation of Werkzeug hashes on PostgreSQL/Supabase.
    password_hash = db.Column(db.Text, nullable=False)
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

    @property
    def normalized_role(self) -> str:
        return (self.role or "").strip().lower()

    def set_password(self, password: str) -> None:
        if not password:
            raise ValueError("Password is required.")
        # pbkdf2 is widely compatible across local and Vercel Python runtimes.
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        if not password or not self.password_hash:
            return False
        stored = str(self.password_hash).strip()
        if not stored:
            return False
        # Accept accidental plaintext inserts (e.g. manual Supabase rows), then
        # callers can re-hash via set_password after a successful login.
        if not stored.startswith(("pbkdf2:", "scrypt:", "sha256:", "sha1:", "md5:")):
            return hmac.compare_digest(stored, password)
        try:
            return check_password_hash(stored, password)
        except (ValueError, TypeError, AttributeError, RuntimeError):
            return False

    def needs_password_rehash(self) -> bool:
        stored = str(self.password_hash or "").strip()
        return not stored.startswith("pbkdf2:sha256")

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role!r}>"
