from datetime import date

from models import Member, db


def get_member_status_skill(member_id: int) -> dict[str, object]:
    """Return minimal membership facts after the caller enforces authorization."""

    member = db.session.get(Member, member_id)
    if member is None:
        return {"found": False, "member_id": member_id}

    return {
        "found": True,
        "member_id": member.id,
        "status": member.status,
        "membership_expires_on": member.membership_expires_on.isoformat(),
        "credit_balance": member.credit_balance,
        "has_active_membership": member.has_active_membership(date.today()),
    }
