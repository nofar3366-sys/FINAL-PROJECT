from sqlalchemy import select

from models import Trainer, User, db


def upgrade_trainer_accounts(default_password: str = "Demo123!") -> int:
    """Ensure trainer profiles have linked User login accounts.

    Legacy SQLite-only table rewrites were removed. Fresh PostgreSQL and
    SQLite databases already include the trainer role and trainers.user_id.
    """

    db.create_all()
    created = 0
    trainers = db.session.scalars(
        select(Trainer).where(Trainer.user_id.is_(None), Trainer.email.is_not(None))
    ).all()
    for trainer in trainers:
        email = User.normalize_email(trainer.email)
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, role="trainer", is_active=trainer.is_active)
            user.set_password(default_password)
            db.session.add(user)
            created += 1
        elif user.role != "trainer":
            continue
        trainer.user = user
    db.session.commit()
    return created
