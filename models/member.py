from datetime import date

from .db import db
from .user import utc_now


class Member(db.Model):
    __tablename__ = "members"
    __table_args__ = (
        db.CheckConstraint("credit_balance >= 0", name="nonnegative_member_credits"),
        db.CheckConstraint(
            "status IN ('active', 'inactive')", name="valid_member_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    first_name = db.Column(
        db.String(80), nullable=False, default="", server_default=""
    )
    last_name = db.Column(
        db.String(80), nullable=False, default="", server_default=""
    )
    phone = db.Column(db.String(30))
    membership_expires_on = db.Column(db.Date, nullable=False)
    credit_balance = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = db.relationship("User", back_populates="member")
    bookings = db.relationship("Booking", back_populates="member")
    renewals = db.relationship(
        "MembershipRenewal",
        back_populates="member",
        order_by="MembershipRenewal.created_at.desc()",
    )
    purchases = db.relationship(
        "MembershipPurchase",
        back_populates="member",
        order_by="MembershipPurchase.purchased_at.desc()",
    )
    subscription = db.relationship(
        "MembershipSubscription",
        back_populates="member",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self) -> str:
        first = (getattr(self, "first_name", None) or "").strip()
        last = (getattr(self, "last_name", None) or "").strip()
        return f"{first} {last}".strip() or "Member"

    def has_active_membership(self, on_date: date | None = None) -> bool:
        effective_date = on_date or date.today()
        return (
            self.status == "active"
            and self.user.is_active
            and self.membership_expires_on >= effective_date
            and (
                self.subscription is None
                or self.subscription.status == "active"
            )
        )

    def __repr__(self) -> str:
        return f"<Member {self.full_name!r}>"
