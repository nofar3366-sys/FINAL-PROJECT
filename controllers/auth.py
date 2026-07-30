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
        session.pop("user_id", None)
        return
    try:
        g.user = db.session.get(User, user_pk)
    except SQLAlchemyError:
        # Keep the session identity; a transient DB blip should not log the user out.
        current_app.logger.exception("Failed to load session user %s", user_pk)
        g.user = None
        return
    if g.user is None or g.user.is_active is False:
        session.pop("user_id", None)
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
    def wrapped_view(*args, **kwargs):
        if g.user.normalized_role != "manager":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def trainer_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if g.user.normalized_role != "trainer" or g.user.trainer is None:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=("GET", "POST"))
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
                "Unable to reach the database. Please try again in a moment.",
                "danger",
            )
            return render_template("login.html")

        active = user is not None and user.is_active is not False
        if user is None or not active or not user.check_password(password):
            flash("Invalid email or password.", "danger")
        else:
            if user.needs_password_rehash():
                try:
                    user.set_password(password)
                    if user.role != user.normalized_role:
                        user.role = user.normalized_role
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    current_app.logger.exception(
                        "Password rehash failed for user %s", user.id
                    )
            session.clear()
            session["user_id"] = int(user.id)
            session.permanent = True
            flash("Welcome back.", "success")
            return _dashboard_redirect(user)

    return render_template("login.html")


@auth_bp.route("/register", methods=("GET", "POST"))
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
        elif db.session.scalar(
            select(User.id).where(func.lower(User.email) == email)
        ):
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
            db.session.add(member)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("An account with this email already exists.", "danger")
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
    endpoints = {
        "manager": "manager.dashboard",
        "trainer": "trainer.dashboard",
        "member": "member.dashboard",
    }
    role = current_user.normalized_role
    endpoint = endpoints.get(role, "member.dashboard")
    return redirect(url_for(endpoint))
