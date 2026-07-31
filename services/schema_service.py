"""Schema compatibility and demo-account repair for SQLite + Supabase."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from models import Member, Trainer, User, db


DEMO_PASSWORD = "Demo123!"
logger = logging.getLogger(__name__)


def repair_database(default_password: str = DEMO_PASSWORD) -> dict[str, object]:
    """Best-effort schema + demo login repair. Never raises to callers."""

    report: dict[str, object] = {"ok": False, "steps": []}
    try:
        db.create_all()
        report["steps"].append("create_all")
    except Exception as exc:
        logger.exception("create_all failed during repair")
        report["create_all_error"] = str(exc)
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        ensure_name_columns()
        report["steps"].append("ensure_name_columns")
    except Exception as exc:
        logger.exception("ensure_name_columns failed during repair")
        report["name_columns_error"] = str(exc)
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        accounts = ensure_demo_accounts(default_password=default_password)
        report["demo_accounts"] = accounts
        report["steps"].append("ensure_demo_accounts")
    except Exception as exc:
        logger.exception("ensure_demo_accounts failed during repair")
        report["demo_accounts_error"] = str(exc)
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        from models.seed import ensure_presentation_seed

        report["presentation"] = ensure_presentation_seed()
        report["steps"].append("ensure_presentation_seed")
    except Exception as exc:
        logger.exception("ensure_presentation_seed failed during repair")
        report["presentation_error"] = str(exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        try:
            from services.membership_service import ensure_default_plans

            ensure_default_plans()
            report["steps"].append("ensure_default_plans")
        except Exception:
            logger.exception("ensure_default_plans failed during repair fallback")
            try:
                db.session.rollback()
            except Exception:
                pass

    report["ok"] = "ensure_name_columns" in report["steps"]
    return report


def upgrade_trainer_accounts(default_password: str = DEMO_PASSWORD) -> int:
    """Ensure trainer profiles have linked User login accounts."""

    try:
        repair_database(default_password=default_password)
    except Exception:
        logger.exception("repair_database failed inside upgrade_trainer_accounts")

    created = 0
    try:
        trainers = db.session.scalars(
            select(Trainer).where(
                Trainer.user_id.is_(None), Trainer.email.is_not(None)
            )
        ).all()
        for trainer in trainers:
            email = User.normalize_email(trainer.email)
            user = db.session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, role="trainer", is_active=trainer.is_active)
                user.set_password(default_password)
                db.session.add(user)
                created += 1
            elif user.normalized_role != "trainer":
                continue
            trainer.user = user
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("upgrade_trainer_accounts failed")
        return 0
    return created


def ensure_name_columns() -> None:
    """Idempotently add first_name/last_name and backfill from full_name if present."""

    inspector = inspect(db.engine)
    for table_name in ("members", "trainers"):
        if table_name not in inspector.get_table_names():
            continue
        # Re-inspect each loop in case a prior ALTER changed the table.
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns(table_name)
        }
        if "first_name" in columns and "last_name" in columns:
            _backfill_empty_names(table_name, columns)
            continue
        _add_name_columns(table_name, columns)


def _add_name_columns(table_name: str, existing_columns: set[str]) -> None:
    dialect = db.engine.dialect.name
    if "first_name" not in existing_columns:
        if dialect == "postgresql":
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN IF NOT EXISTS first_name VARCHAR(80) DEFAULT ''"
                )
            )
        else:
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN first_name VARCHAR(80) DEFAULT ''"
                )
            )
    if "last_name" not in existing_columns:
        if dialect == "postgresql":
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN IF NOT EXISTS last_name VARCHAR(80) DEFAULT ''"
                )
            )
        else:
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN last_name VARCHAR(80) DEFAULT ''"
                )
            )
    db.session.commit()

    columns = {
        column["name"] for column in inspect(db.engine).get_columns(table_name)
    }
    _backfill_empty_names(table_name, columns)


def _backfill_empty_names(table_name: str, columns: set[str]) -> None:
    if "first_name" not in columns or "last_name" not in columns:
        return

    if "full_name" in columns:
        rows = db.session.execute(
            text(f"SELECT id, full_name, first_name, last_name FROM {table_name}")
        ).mappings()
        for row in rows:
            first = (row.get("first_name") or "").strip()
            last = (row.get("last_name") or "").strip()
            if first and last:
                continue
            split_first, split_last = _split_full_name(row.get("full_name"))
            db.session.execute(
                text(
                    f"""
                    UPDATE {table_name}
                    SET first_name = :first_name, last_name = :last_name
                    WHERE id = :row_id
                    """
                ),
                {
                    "first_name": first or split_first,
                    "last_name": last or split_last,
                    "row_id": row["id"],
                },
            )
    else:
        db.session.execute(
            text(
                f"""
                UPDATE {table_name}
                SET first_name = CASE
                        WHEN first_name IS NULL OR TRIM(first_name) = '' THEN 'Unknown'
                        ELSE first_name
                    END,
                    last_name = CASE
                        WHEN last_name IS NULL OR TRIM(last_name) = '' THEN 'User'
                        ELSE last_name
                    END
                """
            )
        )
    db.session.commit()


def ensure_demo_accounts(default_password: str = DEMO_PASSWORD) -> dict[str, str]:
    """Upsert manager/alice/maya so production always has working demo logins."""

    ensure_name_columns()
    actions: dict[str, str] = {}

    manager = _upsert_user("manager@fitness.local", "manager", default_password)
    actions["manager"] = "ready" if manager else "failed"

    alice = _upsert_user("alice@fitness.local", "member", default_password)
    if alice is not None:
        _ensure_member_profile(alice, "Alice", "Active", credit_balance=7, days=120)
        actions["alice"] = "ready"
    else:
        actions["alice"] = "failed"

    maya = _upsert_user("maya@fitness.local", "trainer", default_password)
    if maya is not None:
        _ensure_trainer_profile(
            maya,
            first_name="Maya",
            last_name="Cohen",
            specialty="Yoga and Mobility",
            email="maya@fitness.local",
        )
        actions["maya"] = "ready"
    else:
        actions["maya"] = "failed"

    db.session.commit()
    return actions


def _upsert_user(email: str, role: str, password: str) -> User | None:
    email = User.normalize_email(email)
    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        return user

    user.role = role
    user.is_active = True
    if not user.check_password(password):
        user.set_password(password)
    return user


def _ensure_member_profile(
    user: User,
    first_name: str,
    last_name: str,
    *,
    credit_balance: int,
    days: int,
) -> Member:
    member = user.member
    if member is None:
        member = Member(
            user=user,
            first_name=first_name,
            last_name=last_name,
            membership_expires_on=date.today() + timedelta(days=days),
            credit_balance=credit_balance,
            status="active",
        )
        db.session.add(member)
        db.session.flush()
        return member

    if not (member.first_name or "").strip():
        member.first_name = first_name
    if not (member.last_name or "").strip():
        member.last_name = last_name
    member.status = "active"
    if member.credit_balance < 0:
        member.credit_balance = 0
    if member.membership_expires_on < date.today():
        member.membership_expires_on = date.today() + timedelta(days=days)
    return member


def _ensure_trainer_profile(
    user: User,
    *,
    first_name: str,
    last_name: str,
    specialty: str,
    email: str,
) -> Trainer:
    trainer = user.trainer
    if trainer is None:
        trainer = Trainer(
            user=user,
            first_name=first_name,
            last_name=last_name,
            specialty=specialty,
            email=email,
            is_active=True,
        )
        db.session.add(trainer)
        db.session.flush()
        return trainer

    if not (trainer.first_name or "").strip():
        trainer.first_name = first_name
    if not (trainer.last_name or "").strip():
        trainer.last_name = last_name
    trainer.specialty = specialty or trainer.specialty
    trainer.email = email
    trainer.is_active = True
    return trainer


def _split_full_name(full_name: str | None) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    if not parts:
        return "Unknown", "User"
    if len(parts) == 1:
        return parts[0], "User"
    return parts[0], parts[1]
