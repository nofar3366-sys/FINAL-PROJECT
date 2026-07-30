import csv
from datetime import date, datetime
from io import StringIO

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
from sqlalchemy.exc import IntegrityError

from controllers.auth import manager_required, validate_csrf
from models import (
    Booking,
    Member,
    MembershipPurchase,
    Trainer,
    User,
    WorkoutSession,
    db,
)
from services.ai_service import AIServiceError
from services.cloud_service import CloudUploadError
from services.membership_service import (
    MembershipPurchaseError,
    set_subscription_status,
)
from services.scheduling_service import (
    SchedulingError,
    cancel_session,
    create_session,
)
from skills.scheduling import schedule_recurring_sessions_skill


manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


@manager_bp.get("/dashboard")
@manager_required
def dashboard():
    counts = {
        "members": db.session.scalar(select(func.count(Member.id))),
        "trainers": db.session.scalar(select(func.count(Trainer.id))),
        "sessions": db.session.scalar(select(func.count(WorkoutSession.id))),
        "bookings": db.session.scalar(
            select(func.count(Booking.id)).where(Booking.status == "booked")
        ),
        "revenue_cents": db.session.scalar(
            select(func.coalesce(func.sum(MembershipPurchase.amount_paid_cents), 0))
        ),
    }
    members = db.session.scalars(
        select(Member).order_by(Member.created_at.desc()).limit(5)
    ).all()
    trainers = db.session.scalars(
        select(Trainer).order_by(Trainer.created_at.desc()).limit(5)
    ).all()
    return render_template(
        "dashboard.html",
        counts=counts,
        members=members,
        trainers=trainers,
        cloud_status=request.args.get("cloud_status"),
        cloud_reference=request.args.get("cloud_reference"),
        cloud_url=request.args.get("cloud_url"),
        cloud_snapshot_url=request.args.get("cloud_snapshot_url"),
    )


@manager_bp.get("/members")
@manager_required
def members():
    search = request.args.get("q", "").strip()
    query = select(Member).join(Member.user).order_by(Member.full_name)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(Member.full_name.ilike(term), User.email.ilike(term))
        )
    return render_template(
        "members.html", members=db.session.scalars(query).all(), search=search
    )


@manager_bp.route("/members/new", methods=("GET", "POST"))
@manager_required
def new_member():
    if request.method == "POST":
        validate_csrf()
        values, error = _member_form_values(require_password=True)
        if error:
            flash(error, "danger")
        elif db.session.scalar(select(User.id).where(User.email == values["email"])):
            flash("An account with this email already exists.", "danger")
        else:
            user = User(
                email=values["email"], role="member", is_active=values["is_active"]
            )
            user.set_password(values["password"])
            member = Member(
                user=user,
                full_name=values["full_name"],
                phone=values["phone"],
                membership_expires_on=values["expiry"],
                credit_balance=values["credits"],
                status=values["status"],
            )
            db.session.add(member)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("The member could not be created.", "danger")
            else:
                flash("Member created.", "success")
                return redirect(url_for("manager.member_detail", member_id=member.id))

    return render_template("member_form.html", member=None)


@manager_bp.get("/members/<int:member_id>")
@manager_required
def member_detail(member_id: int):
    member = db.get_or_404(Member, member_id)
    return render_template("member_detail.html", member=member)


@manager_bp.route("/members/<int:member_id>/edit", methods=("GET", "POST"))
@manager_required
def edit_member(member_id: int):
    member = db.get_or_404(Member, member_id)
    if request.method == "POST":
        validate_csrf()
        values, error = _member_form_values(require_password=False)
        duplicate = (
            db.session.scalar(
                select(User.id).where(
                    User.email == values["email"], User.id != member.user_id
                )
            )
            if not error
            else None
        )
        if error:
            flash(error, "danger")
        elif duplicate:
            flash("An account with this email already exists.", "danger")
        else:
            member.user.email = values["email"]
            member.user.is_active = values["is_active"]
            member.full_name = values["full_name"]
            member.phone = values["phone"]
            member.membership_expires_on = values["expiry"]
            member.credit_balance = values["credits"]
            member.status = values["status"]
            db.session.commit()
            flash("Member updated.", "success")
            return redirect(url_for("manager.member_detail", member_id=member.id))

    return render_template("member_form.html", member=member)


@manager_bp.post("/members/<int:member_id>/deactivate")
@manager_required
def deactivate_member(member_id: int):
    validate_csrf()
    member = db.get_or_404(Member, member_id)
    member.status = "inactive"
    member.user.is_active = False
    db.session.commit()
    flash("Member deactivated.", "success")
    return redirect(url_for("manager.member_detail", member_id=member.id))


@manager_bp.post("/members/<int:member_id>/activate")
@manager_required
def activate_member(member_id: int):
    validate_csrf()
    member = db.get_or_404(Member, member_id)
    member.status = "active"
    member.user.is_active = True
    db.session.commit()
    flash("Member activated.", "success")
    return redirect(url_for("manager.member_detail", member_id=member.id))


@manager_bp.get("/trainers")
@manager_required
def trainers():
    search = request.args.get("q", "").strip()
    query = select(Trainer).order_by(Trainer.full_name)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(Trainer.full_name.ilike(term), Trainer.specialty.ilike(term))
        )
    return render_template(
        "trainers.html", trainers=db.session.scalars(query).all(), search=search
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
            user = User(email=values["email"], role="trainer", is_active=values["is_active"])
            user.set_password(password)
            trainer = Trainer(user=user, **values)
            db.session.add(trainer)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("A trainer with this email already exists.", "danger")
            else:
                flash("Trainer created.", "success")
                return redirect(
                    url_for("manager.trainer_detail", trainer_id=trainer.id)
                )

    return render_template("trainer_form.html", trainer=None)


@manager_bp.get("/trainers/<int:trainer_id>")
@manager_required
def trainer_detail(trainer_id: int):
    trainer = db.get_or_404(Trainer, trainer_id)
    return render_template("trainer_detail.html", trainer=trainer)


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
            for field, value in values.items():
                setattr(trainer, field, value)
            if trainer.user is None:
                trainer.user = User(
                    email=values["email"],
                    role="trainer",
                    is_active=values["is_active"],
                )
                trainer.user.set_password(password)
            else:
                trainer.user.email = values["email"]
                trainer.user.is_active = values["is_active"]
                if password:
                    trainer.user.set_password(password)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("A trainer with this email already exists.", "danger")
            else:
                flash("Trainer updated.", "success")
                return redirect(
                    url_for("manager.trainer_detail", trainer_id=trainer.id)
                )

    return render_template("trainer_form.html", trainer=trainer)


@manager_bp.post("/trainers/<int:trainer_id>/deactivate")
@manager_required
def deactivate_trainer(trainer_id: int):
    validate_csrf()
    trainer = db.get_or_404(Trainer, trainer_id)
    trainer.is_active = False
    if trainer.user:
        trainer.user.is_active = False
    db.session.commit()
    flash("Trainer deactivated.", "success")
    return redirect(url_for("manager.trainer_detail", trainer_id=trainer.id))


@manager_bp.post("/trainers/<int:trainer_id>/activate")
@manager_required
def activate_trainer(trainer_id: int):
    validate_csrf()
    trainer = db.get_or_404(Trainer, trainer_id)
    trainer.is_active = True
    if trainer.user:
        trainer.user.is_active = True
    db.session.commit()
    flash("Trainer activated.", "success")
    return redirect(url_for("manager.trainer_detail", trainer_id=trainer.id))


@manager_bp.get("/sessions")
@manager_required
def sessions():
    workout_sessions = db.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.starts_at)
    ).all()
    trainers = db.session.scalars(
        select(Trainer)
        .where(Trainer.is_active.is_(True))
        .order_by(Trainer.full_name)
    ).all()
    return render_template(
        "sessions.html", sessions=workout_sessions, trainers=trainers
    )


@manager_bp.route("/sessions/new", methods=("GET", "POST"))
@manager_required
def new_session():
    trainers = db.session.scalars(
        select(Trainer)
        .where(Trainer.is_active.is_(True))
        .order_by(Trainer.full_name)
    ).all()
    if request.method == "POST":
        validate_csrf()
        try:
            create_session(
                trainer_id=int(request.form.get("trainer_id", "0")),
                title=request.form.get("title", ""),
                starts_at=datetime.fromisoformat(request.form.get("starts_at", "")),
                duration_minutes=int(request.form.get("duration_minutes", "60")),
                max_capacity=int(request.form.get("max_capacity", "0")),
            )
        except (ValueError, SchedulingError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Workout session created.", "success")
            return redirect(url_for("manager.sessions"))
    return render_template("session_form.html", trainers=trainers)


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
    trainer_names = db.session.scalars(
        select(Trainer.full_name).where(Trainer.is_active.is_(True))
    ).all()
    try:
        parsed = current_app.extensions["ai_service"].parse_schedule_command(
            prompt, trainer_names
        )
        result = schedule_recurring_sessions_skill(
            trainer_name=str(parsed["trainer_name"]),
            title=str(parsed["title"]),
            weekday=str(parsed["weekday"]),
            start_time=str(parsed["start_time"]),
            max_capacity=int(parsed["max_capacity"]),
            occurrences=4,
            duration_minutes=int(parsed.get("duration_minutes", 60)),
        )
    except (KeyError, TypeError, ValueError, AIServiceError, SchedulingError) as exc:
        db.session.rollback()
        flash(f"AI scheduling failed: {exc}", "danger")
    else:
        flash(
            f"AI scheduling created {result['created_count']} weekly sessions.",
            "success",
        )
    return redirect(url_for("manager.sessions"))


@manager_bp.get("/subscriptions")
@manager_required
def subscriptions():
    members = db.session.scalars(select(Member).order_by(Member.full_name)).all()
    return render_template("subscriptions.html", members=members)


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


@manager_bp.post("/cloud-backup")
@manager_required
def cloud_backup():
    validate_csrf()
    try:
        database_path = db.engine.url.database
        result = current_app.extensions["cloud_service"].backup_database(database_path)
    except (CloudUploadError, FileNotFoundError, OSError) as exc:
        flash(f"Cloud backup failed: {exc}", "danger")
        return redirect(url_for("manager.dashboard"))

    flash(result.message, "success")
    return redirect(
        url_for(
            "manager.dashboard",
            cloud_status=result.status,
            cloud_reference=result.reference,
            cloud_url=result.secure_url,
            cloud_snapshot_url=result.readable_url,
        )
    )


@manager_bp.get("/reports.csv")
@manager_required
def reports_csv():
    output = StringIO()
    writer = csv.writer(output)
    purchases = db.session.scalars(
        select(MembershipPurchase).order_by(MembershipPurchase.purchased_at)
    ).all()
    workout_sessions = db.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.starts_at)
    ).all()

    writer.writerow(["Fitness Studio Operational Report"])
    writer.writerow(["Generated", datetime.now().isoformat(timespec="seconds")])
    writer.writerow([])
    writer.writerow(["Revenue"])
    writer.writerow(["Purchase ID", "Member", "Plan", "Amount", "Purchased"])
    for purchase in purchases:
        writer.writerow(
            [
                purchase.id,
                purchase.member.full_name,
                purchase.plan.name,
                f"{purchase.amount_paid_cents / 100:.2f}",
                purchase.purchased_at.isoformat(),
            ]
        )
    writer.writerow([])
    writer.writerow(["Attendance and Capacity"])
    writer.writerow(
        ["Session ID", "Title", "Trainer", "Starts", "Status", "Booked", "Capacity"]
    )
    for workout_session in workout_sessions:
        writer.writerow(
            [
                workout_session.id,
                workout_session.title,
                workout_session.trainer.full_name,
                workout_session.starts_at.isoformat(),
                workout_session.status,
                workout_session.active_booking_count,
                workout_session.max_capacity,
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=fitness-studio-report.csv"
        },
    )


def _member_form_values(require_password: bool):
    email = User.normalize_email(request.form.get("email", ""))
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip() or None
    password = request.form.get("password", "")
    status = request.form.get("status", "active")
    try:
        expiry = date.fromisoformat(request.form.get("membership_expires_on", ""))
        credits = int(request.form.get("credit_balance", "0"))
    except ValueError:
        return {}, "Enter a valid expiry date and credit balance."

    error = None
    if not full_name:
        error = "Full name is required."
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
        "full_name": full_name,
        "phone": phone,
        "password": password,
        "expiry": expiry,
        "credits": credits,
        "status": status,
        "is_active": status == "active",
    }, error


def _trainer_form_values(require_password: bool = False):
    full_name = request.form.get("full_name", "").strip()
    specialty = request.form.get("specialty", "").strip()
    email = User.normalize_email(request.form.get("email", ""))
    phone = request.form.get("phone", "").strip() or None
    is_active = request.form.get("is_active", "1") == "1"
    password = request.form.get("password", "")

    error = None
    if not full_name:
        error = "Trainer name is required."
    elif not specialty:
        error = "Specialty is required."
    elif "@" not in email:
        error = "Enter a valid email address."
    elif require_password and len(password) < 6:
        error = "Trainer login password must contain at least 6 characters."
    elif password and len(password) < 6:
        error = "Trainer login password must contain at least 6 characters."

    return {
        "full_name": full_name,
        "specialty": specialty,
        "email": email,
        "phone": phone,
        "is_active": is_active,
    }, password, error
