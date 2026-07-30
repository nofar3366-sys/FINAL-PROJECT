from sqlalchemy import inspect, select, text

from models import Trainer, User, db


def upgrade_trainer_accounts(default_password: str = "Demo123!") -> int:
    """Upgrade an existing SQLite database and create missing trainer logins."""

    if db.engine.dialect.name != "sqlite":
        raise RuntimeError("This academic project supports SQLite only.")

    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        db.create_all()
        return 0

    user_table_sql = db.session.execute(
        text(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        )
    ).scalar_one()
    trainer_columns = {column["name"] for column in inspector.get_columns("trainers")}

    if "'trainer'" not in user_table_sql or "user_id" not in trainer_columns:
        db.session.remove()
        connection = db.engine.raw_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            if "'trainer'" not in user_table_sql:
                cursor.executescript(
                    """
                    CREATE TABLE users_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL,
                        CONSTRAINT valid_user_role
                            CHECK (role IN ('manager', 'member', 'trainer')),
                        CONSTRAINT valid_user_active CHECK (is_active IN (0, 1))
                    );
                    INSERT INTO users_new
                        (id, email, password_hash, role, is_active, created_at)
                    SELECT id, email, password_hash, role, is_active, created_at
                    FROM users;
                    DROP TABLE users;
                    ALTER TABLE users_new RENAME TO users;
                    CREATE INDEX ix_users_email ON users (email);
                    """
                )
            if "user_id" not in trainer_columns:
                cursor.execute(
                    "ALTER TABLE trainers ADD COLUMN user_id INTEGER "
                    "REFERENCES users(id) ON DELETE RESTRICT"
                )
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_trainers_user_id ON trainers (user_id)"
                )
            connection.commit()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    db.session.remove()
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
