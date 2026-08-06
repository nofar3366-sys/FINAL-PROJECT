from datetime import date, datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from controllers.auth import manager_required, validate_csrf
from controllers.safe_db import recover_from_db_error
from models import Member, Trainer, User, db
from models.time_utils import ensure_utc
from services.manager_service import (
    ManagerServiceError,
    create_member,
    create_trainer,
    generate_ai_schedule,
    generate_operational_report,
    get_active_trainers,
    get_dashboard_context,
    get_sessions_context,
    get_subscription_members,
    set_member_active,
    set_trainer_active,
    update_member,
    update_trainer,
)
from services.membership_service import (
    MembershipPurchaseError,
    set_subscription_status,
)
from services.scheduling_service import (
    SchedulingError,
    cancel_session,
    create_session,
)


manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


@manager_bp.get("/dashboard")
@manager_required
def dashboard():
    try:
        context = get_dashboard_context()
    except SQLAlchemyError:
        current_app.logger.exception("Manager dashboard query failed")
        recover_from_db_error()
        return redirect(url_for("auth.login"))
    return render_template("manager/dashboard.html", **context)


@manager_bp.get("/members")
@manager_required
def members():
    search = request.args.get("q", "").strip()
    query = select(Member).join(Member.user).order_by(
        Member.first_name, Member.last_name
    )
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Member.first_name.ilike(term),
                Member.last_name.ilike(term),
                func.concat(Member.first_name, " ", Member.last_name).ilike(term),
                User.email.ilike(term),
            )
        )
    return render_template(
        "manager/members.html",
        members=db.session.scalars(query).all(),
        search=search,
    )


@manager_bp.route("/members/new", methods=("GET", "POST"))
@manager_required
def new_member():
    if request.method == "POST":
        validate_csrf()
        values, error = _member_form_values(require_password=True)
        if error:
            flash(error, "danger")
        else:
            try:
                member = create_member(values)
            except ManagerServiceError as exc:
                flash(str(exc), "danger")
            else:
                flash("Member created.", "success")
                return redirect(url_for("manager.member_detail", member_id=member.id))

    return render_template("manager/member_form.html", member=None)


@manager_bp.get("/members/<int:member_id>")
@manager_required
def member_detail(member_id: int):
    member = db.get_or_404(Member, member_id)
    return render_template("manager/member_detail.html", member=member)


@manager_bp.route("/members/<int:member_id>/edit", methods=("GET", "POST"))
@manager_required
def edit_member(member_id: int):
    member = db.get_or_404(Member, member_id)
    if request.method == "POST":
        validate_csrf()
        values, error = _member_form_values(require_password=False)
        if error:
            flash(error, "danger")
        else:
            try:
                update_member(member, values)
            except ManagerServiceError as exc:
                flash(str(exc), "danger")
            else:
                flash("Member updated.", "success")
                return redirect(
                    url_for("manager.member_detail", member_id=member.id)
                )

    return render_template("manager/member_form.html", member=member)


@manager_bp.post("/members/<int:member_id>/deactivate")
@manager_required
def deactivate_member(member_id: int):
    validate_csrf()
    member = db.get_or_404(Member, member_id)
    set_member_active(member, False)
    flash("Member deactivated.", "success")
    return redirect(url_for("manager.member_detail", member_id=member.id))


@manager_bp.post("/members/<int:member_id>/activate")
@manager_required
def activate_member(member_id: int):
    validate_csrf()
    member = db.get_or_404(Member, member_id)
    set_member_active(member, True)
    flash("Member activated.", "success")
    return redirect(url_for("manager.member_detail", member_id=member.id))


@manager_bp.get("/trainers")
@manager_required
def trainers():
    search = request.args.get("q", "").strip()
    query = select(Trainer).order_by(Trainer.first_name, Trainer.last_name)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Trainer.first_name.ilike(term),
                Trainer.last_name.ilike(term),
                func.concat(Trainer.first_name, " ", Trainer.last_name).ilike(term),
                Trainer.specialty.ilike(term),
            )
        )
    return render_template(
        "manager/trainers.html",
        trainers=db.session.scalars(query).all(),
        search=search,
    )


@manager_bp.route("/trainers/new", methods=("GET", "POST"))
@manager_required
def new_trainer():
    if request.method == "POST":
        validate_csrf()
        values, password, error = _trainer_form_values(require_password=True)
        if error:
            flash(error, "danger")
        else:
            try:
                trainer = create_trainer(values, password)
            except ManagerServiceError as exc:
                flash(str(exc), "danger")
            else:
                flash("Trainer created.", "success")
                return redirect(
                    url_for("manager.trainer_detail", trainer_id=trainer.id)
                )

    return render_template("manager/trainer_form.html", trainer=None)


@manager_bp.get("/trainers/<int:trainer_id>")
@manager_required
def trainer_detail(trainer_id: int):
    trainer = db.get_or_404(Trainer, trainer_id)
    return render_template("manager/trainer_detail.html", trainer=trainer)


@manager_bp.route("/trainers/<int:trainer_id>/edit", methods=("GET", "POST"))
@manager_required
def edit_trainer(trainer_id: int):
    trainer = db.get_or_404(Trainer, trainer_id)
    if request.method == "POST":
        validate_csrf()
        values, password, error = _trainer_form_values(
            require_password=trainer.user is None
        )
        if error:
            flash(error, "danger")
        else:
            try:
                update_trainer(trainer, values, password)
            except ManagerServiceError as exc:
                flash(str(exc), "danger")
            else:
                flash("Trainer updated.", "success")
                return redirect(
                    url_for("manager.trainer_detail", trainer_id=trainer.id)
                )

    return render_template("manager/trainer_form.html", trainer=trainer)


@manager_bp.post("/trainers/<int:trainer_id>/deactivate")
@manager_required
def deactivate_trainer(trainer_id: int):
    validate_csrf()
    trainer = db.get_or_404(Trainer, trainer_id)
    set_trainer_active(trainer, False)
    flash("Trainer deactivated.", "success")
    return redirect(url_for("manager.trainer_detail", trainer_id=trainer.id))


@manager_bp.post("/trainers/<int:trainer_id>/activate")
@manager_required
def activate_trainer(trainer_id: int):
    validate_csrf()
    trainer = db.get_or_404(Trainer, trainer_id)
    set_trainer_active(trainer, True)
    flash("Trainer activated.", "success")
    return redirect(url_for("manager.trainer_detail", trainer_id=trainer.id))


@manager_bp.get("/sessions")
@manager_required
def sessions():
    return render_template("manager/sessions.html", **get_sessions_context())


@manager_bp.route("/sessions/new", methods=("GET", "POST"))
@manager_required
def new_session():
    trainers = get_active_trainers()
    if request.method == "POST":
        validate_csrf()
        try:
            raw_starts = (request.form.get("starts_at") or "").strip()
            if not raw_starts:
                raise ValueError("Choose a date and time for the session.")
            create_session(
                trainer_id=int(request.form.get("trainer_id") or "0"),
                title=request.form.get("title", ""),
                starts_at=ensure_utc(datetime.fromisoformat(raw_starts)),
                duration_minutes=int(request.form.get("duration_minutes") or "60"),
                max_capacity=int(request.form.get("max_capacity") or "0"),
            )
        except (ValueError, SchedulingError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception as exc:
            # Do not treat form/scheduling bugs as a "database repair" logout.
            db.session.rollback()
            current_app.logger.exception("Create session failed")
            flash(f"Could not create the session: {exc}", "danger")
        else:
            flash("Workout session created.", "success")
            return redirect(url_for("manager.sessions"))
    return render_template("manager/session_form.html", trainers=trainers)


@manager_bp.post("/sessions/<int:session_id>/cancel")
@manager_required
def cancel_workout_session(session_id: int):
    validate_csrf()
    try:
        cancel_session(session_id)
    except SchedulingError as exc:
        flash(str(exc), "danger")
    else:
        flash("Session cancelled and eligible credits refunded.", "success")
    return redirect(url_for("manager.sessions"))


@manager_bp.post("/sessions/ai-schedule")
@manager_required
def ai_schedule():
    validate_csrf()
    prompt = request.form.get("prompt", "").strip()
    try:
        category, message = generate_ai_schedule(
            prompt, current_app.extensions["ai_service"]
        )
    except ManagerServiceError as exc:
        current_app.logger.exception("Fallback workout generation failed")
        flash(str(exc), "danger")
    else:
        flash(message, category)
    return redirect(url_for("manager.sessions"))


@manager_bp.get("/subscriptions")
@manager_required
def subscriptions():
    return render_template(
        "manager/subscriptions.html", members=get_subscription_members()
    )


@manager_bp.post("/subscriptions/<int:member_id>/<status>")
@manager_required
def update_subscription(member_id: int, status: str):
    validate_csrf()
    try:
        set_subscription_status(member_id, status)
    except (ValueError, MembershipPurchaseError) as exc:
        flash(str(exc), "danger")
    else:
        flash(f"Subscription marked {status}.", "success")
    return redirect(url_for("manager.subscriptions"))


@manager_bp.get("/reports.csv")
@manager_required
def reports_csv():
    return Response(
        generate_operational_report(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=fitness-studio-report.csv"
        },
    )


def _member_form_values(require_password: bool):
    email = User.normalize_email(request.form.get("email", ""))
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip() or None
    password = request.form.get("password", "")
    status = request.form.get("status", "active")
    try:
        expiry = date.fromisoformat(request.form.get("membership_expires_on", ""))
        credits = int(request.form.get("credit_balance", "0"))
    except ValueError:
        return {}, "Enter a valid expiry date and credit balance."

    error = None
    if not first_name:
        error = "First name is required."
    elif not last_name:
        error = "Last name is required."
    elif "@" not in email:
        error = "Enter a valid email address."
    elif require_password and len(password) < 6:
        error = "Password must contain at least 6 characters."
    elif credits < 0:
        error = "Credit balance cannot be negative."
    elif status not in {"active", "inactive"}:
        error = "Invalid member status."

    return {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "password": password,
        "expiry": expiry,
        "credits": credits,
        "status": status,
        "is_active": status == "active",
    }, error


def _trainer_form_values(require_password: bool = False):
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    specialty = request.form.get("specialty", "").strip()
    email = User.normalize_email(request.form.get("email", ""))
    phone = request.form.get("phone", "").strip() or None
    is_active = request.form.get("is_active", "1") == "1"
    password = request.form.get("password", "")

    error = None
    if not first_name:
        error = "First name is required."
    elif not last_name:
        error = "Last name is required."
    elif not specialty:
        error = "Specialty is required."
    elif "@" not in email:
        error = "Enter a valid email address."
    elif require_password and len(password) < 6:
        error = "Trainer login password must contain at least 6 characters."
    elif password and len(password) < 6:
        error = "Trainer login password must contain at least 6 characters."

    return {
        "first_name": first_name,
        "last_name": last_name,
        "specialty": specialty,
        "email": email,
        "phone": phone,
        "is_active": is_active,
    }, password, error
