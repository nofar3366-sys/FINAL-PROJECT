from .db import db
from .user import utc_now


class MembershipRenewal(db.Model):
    __tablename__ = "membership_renewals"
    __table_args__ = (
        db.CheckConstraint(
            "credits_added >= 0", name="nonnegative_renewal_credits"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    processed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    previous_expiry = db.Column(db.Date, nullable=False)
    new_expiry = db.Column(db.Date, nullable=False)
    credits_added = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    member = db.relationship("Member", back_populates="renewals")
    processed_by = db.relationship("User", back_populates="processed_renewals")

    def __repr__(self) -> str:
        return (
            f"<MembershipRenewal member_id={self.member_id} "
            f"new_expiry={self.new_expiry!r}>"
        )
