from sqlalchemy import text

from models import db


def begin_write_transaction() -> None:
    """Start a write transaction in a dialect-safe way.

    SQLite uses BEGIN IMMEDIATE to lock early for capacity/credit updates.
    PostgreSQL starts a normal transaction; row locks can still be applied by
    callers with Query.with_for_update() when needed.
    """

    db.session.rollback()
    if db.engine.dialect.name == "sqlite":
        db.session.execute(text("BEGIN IMMEDIATE"))
