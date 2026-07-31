import hmac
import secrets
from datetime import date
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from controllers.safe_db import db_safe, recover_from_db_error
from models import Member, User, db


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_hex(24)
        session["_csrf_token"] = token
    return token


def validate_csrf() -> None:
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    submitted = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    if not expected or not hmac.compare_digest(submitted, expected):
        abort(400, description="Invalid form token.")


def clear_invalid_session(message: str | None = None) -> None:
    session.clear()
    if message:
        flash(message, "warning")


@auth_bp.app_context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@auth_bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None
    if user_id is None:
        return
    try:
        user_pk = int(user_id)
    except (TypeError, ValueError):
        clear_invalid_session("Your session was invalid. Please sign in again.")
        return
    try:
        g.user = db.session.get(User, user_pk)
        # Touch role-specific profiles early so schema mismatches fail here,
        # not as an unhandled 500 inside a dashboard template.
        if g.user is not None:
            _ = g.user.normalized_role
            if g.user.normalized_role == "member":
                _ = g.user.member
            elif g.user.normalized_role == "trainer":
                _ = g.user.trainer
    except SQLAlchemyError:
        current_app.logger.exception("Failed to load session user %s", user_pk)
        recover_from_db_error(
            "Your session could not be loaded because the database schema "
            "was out of date. Please sign in again.",
            clear_auth_session=True,
        )
        g.user = None
        return
    except Exception:
        # Invalid/orphaned sessions or unexpected ORM state must never 500.
        current_app.logger.exception("Unexpected session load failure for %s", user_pk)
        clear_invalid_session(
            "Your session could not be loaded. Please sign in again."
        )
        g.user = None
        return
    if g.user is None or g.user.is_active is False:
        clear_invalid_session(
            "Your session expired or the account is no longer available. "
            "Please sign in again."
        )
        g.user = None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def manager_required(view):
    @wraps(view)
    @login_required
    @db_safe
    def wrapped_view(*args, **kwargs):
        if g.user.normalized_role != "manager":
            flash("That page is only available to managers.", "warning")
            return _dashboard_redirect()
        return view(*args, **kwargs)

    return wrapped_view


def trainer_required(view):
    @wraps(view)
    @login_required
    @db_safe
    def wrapped_view(*args, **kwargs):
        try:
            role = g.user.normalized_role
            trainer = g.user.trainer
        except SQLAlchemyError:
            current_app.logger.exception("Trainer profile lookup failed")
            recover_from_db_error(clear_auth_session=True)
            return redirect(url_for("auth.login"))
        except Exception:
            current_app.logger.exception("Unexpected trainer guard failure")
            clear_invalid_session(
                "Your trainer session could not be verified. Please sign in again."
            )
            return redirect(url_for("auth.login"))
        if role != "trainer":
            flash("That page is only available to trainers.", "warning")
            return _dashboard_redirect()
        if trainer is None:
            clear_invalid_session(
                "Your trainer profile is missing. Please sign in again after "
                "the studio data is restored."
            )
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def member_required(view):
    @wraps(view)
    @login_required
    @db_safe
    def wrapped_view(*args, **kwargs):
        try:
            role = g.user.normalized_role
            member = g.user.member
        except SQLAlchemyError:
            current_app.logger.exception("Member profile lookup failed")
            recover_from_db_error(clear_auth_session=True)
            return redirect(url_for("auth.login"))
        except Exception:
            current_app.logger.exception("Unexpected member guard failure")
            clear_invalid_session(
                "Your member session could not be verified. Please sign in again."
            )
            return redirect(url_for("auth.login"))
        if role != "member":
            flash("That page is only available to members.", "warning")
            return _dashboard_redirect()
        if member is None:
            clear_invalid_session(
                "Your member profile is missing. Please sign in again after "
                "the studio data is restored, or register a new account."
            )
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=("GET", "POST"))
@db_safe
def login():
    if g.user is not None:
        return _dashboard_redirect()

    if request.method == "POST":
        validate_csrf()
        email = User.normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        user = None
        try:
            user = db.session.scalar(
                select(User).where(func.lower(User.email) == email)
            )
        except SQLAlchemyError:
            current_app.logger.exception("Login lookup failed for %s", email)
            flash(
                "Unable to reach the database. Please try again in a moment. "
                "If this persists, the configured DATABASE_URL may be invalid.",
                "danger",
            )
            return render_template("login.html")

        active = user is not None and user.is_active is not False
        if user is None or not active or not user.check_password(password):
            flash("Invalid email or password.", "danger")
        else:
            try:
                if user.needs_password_rehash():
                    user.set_password(password)
                    if user.role != user.normalized_role:
                        user.role = user.normalized_role
                    db.session.commit()
                role = user.normalized_role
                member = user.member if role == "member" else None
                trainer = user.trainer if role == "trainer" else None
            except SQLAlchemyError:
                current_app.logger.exception("Login profile check failed")
                recover_from_db_error(
                    "Login could not finish because the database needed repair. "
                    "Please try signing in once more."
                )
                return redirect(url_for("auth.login"))

            if role == "member" and member is None:
                flash(
                    "This account has no member profile. Ask a manager to "
                    "recreate it, or register again.",
                    "danger",
                )
            elif role == "trainer" and trainer is None:
                flash(
                    "This account has no trainer profile. Ask a manager to "
                    "recreate the trainer login.",
                    "danger",
                )
            else:
                session.clear()
                session["user_id"] = int(user.id)
                session.permanent = True
                flash("Welcome back.", "success")
                return _dashboard_redirect(user)

    return render_template("login.html")


@auth_bp.route("/register", methods=("GET", "POST"))
@db_safe
def register():
    if g.user is not None:
        return _dashboard_redirect()

    if request.method == "POST":
        validate_csrf()
        email = User.normalize_email(request.form.get("email", ""))
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        error = None
        if not first_name:
            error = "First name is required."
        elif not last_name:
            error = "Last name is required."
        elif "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 6:
            error = "Password must contain at least 6 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            try:
                exists = db.session.scalar(
                    select(User.id).where(func.lower(User.email) == email)
                )
            except SQLAlchemyError:
                current_app.logger.exception("Register lookup failed")
                flash(
                    "Unable to reach the database. Please try again in a moment.",
                    "danger",
                )
                return render_template("register.html")
            if exists:
                error = "An account with this email already exists."

        if error:
            flash(error, "danger")
        else:
            user = User(email=email, role="member", is_active=True)
            user.set_password(password)
            member = Member(
                user=user,
                first_name=first_name,
                last_name=last_name,
                phone=phone or None,
                membership_expires_on=date.today(),
                credit_balance=0,
                status="active",
            )
            # Explicitly stage both 1NF records in the same transaction.
            db.session.add_all([user, member])
            try:
                db.session.flush()
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("An account with this email already exists.", "danger")
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception("Registration insert failed")
                recover_from_db_error(
                    "Registration failed because the database needed repair. "
                    "Please try again."
                )
                return redirect(url_for("auth.register"))
            else:
                flash(
                    "Registration complete. A manager can renew your membership.",
                    "success",
                )
                return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


def _dashboard_redirect(user=None):
    current_user = user or g.user
    if current_user is None:
        return redirect(url_for("auth.login"))
    endpoints = {
        "manager": "manager.dashboard",
        "trainer": "trainer.dashboard",
        "member": "member.dashboard",
    }
    role = current_user.normalized_role
    endpoint = endpoints.get(role)
    if endpoint is None:
        clear_invalid_session(
            "Your account role is not recognized. Please sign in again."
        )
        return redirect(url_for("auth.login"))
    return redirect(url_for(endpoint))
