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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
    g.user = db.session.get(User, user_id) if user_id else None


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
        if g.user.role != "manager":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def trainer_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if g.user.role != "trainer" or g.user.trainer is None:
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
        user = db.session.scalar(select(User).where(User.email == email))

        if user is None or not user.is_active or not user.check_password(password):
            flash("Invalid email or password.", "danger")
        else:
            session.clear()
            session["user_id"] = user.id
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
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        error = None
        if not full_name:
            error = "Full name is required."
        elif "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 6:
            error = "Password must contain at least 6 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif db.session.scalar(select(User.id).where(User.email == email)):
            error = "An account with this email already exists."

        if error:
            flash(error, "danger")
        else:
            user = User(email=email, role="member", is_active=True)
            user.set_password(password)
            member = Member(
                user=user,
                full_name=full_name,
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
    endpoint = endpoints[current_user.role]
    return redirect(url_for(endpoint))
