from datetime import date, datetime, timedelta

from sqlalchemy import select

from models import Member, Trainer, User, WorkoutSession, db
from models.seed import seed_demo_data


def login(client, email="manager@fitness.local", password="Demo123!"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_manager_login_logout_and_role_protection(app):
    seed_demo_data()
    client = app.test_client()

    response = login(client)
    assert response.status_code == 200
    assert b"Manager dashboard" in response.data

    response = client.post("/auth/logout", follow_redirects=True)
    assert b"Sign in" in response.data

    response = login(client, "alice@fitness.local")
    assert b"Welcome, Alice Active" in response.data
    schedule = client.get("/member/schedule")
    assert b"Weekly Class Schedule" in schedule.data
    assert schedule.data.count(b'class="calendar-day"') == 7
    assert b"Sunday" in schedule.data and b"Saturday" in schedule.data
    assert b"No workouts" in schedule.data
    assert b"Choose your training plan" in client.get("/member/renewal").data
    assert b"Studio Assistant" in client.get("/member/assistant").data
    recommendation = client.post(
        "/member/assistant/recommend",
        data={"goal": "improve strength as a beginner"},
    )
    assert b"Workout Recommendation Agent" in recommendation.data
    assert b"Recommendation:" in recommendation.data
    skill_response = client.post(
        "/member/assistant/availability",
        data={
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "specialty": "Yoga",
        },
    )
    assert b"Skill executed: get_class_availability_skill" in skill_response.data
    assert client.get("/manager/members").status_code == 403


def test_public_registration_creates_zero_credit_member(app):
    client = app.test_client()
    response = client.post(
        "/auth/register",
        data={
            "first_name": "New",
            "last_name": "Member",
            "email": "new@example.com",
            "phone": "050-111-2222",
            "password": "secret7",
            "confirm_password": "secret7",
        },
        follow_redirects=True,
    )
    assert b"Registration complete" in response.data

    member = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "new@example.com")
    )
    assert member is not None
    assert member.first_name == "New"
    assert member.last_name == "Member"
    assert member.full_name == "New Member"
    assert member.credit_balance == 0
    assert member.membership_expires_on == date.today()
    assert member.user.check_password("secret7")


def test_manager_can_create_member_and_trainer(app):
    seed_demo_data()
    client = app.test_client()
    login(client)

    expiry = date.today() + timedelta(days=30)
    response = client.post(
        "/manager/members/new",
        data={
            "first_name": "Managed",
            "last_name": "Member",
            "email": "managed@example.com",
            "phone": "",
            "password": "secret8",
            "membership_expires_on": expiry.isoformat(),
            "credit_balance": "6",
            "status": "active",
        },
        follow_redirects=True,
    )
    assert b"Member created" in response.data
    managed = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "managed@example.com")
    )
    assert managed is not None
    assert managed.first_name == "Managed"
    assert managed.last_name == "Member"

    response = client.post(
        "/manager/trainers/new",
        data={
            "first_name": "Test",
            "last_name": "Trainer",
            "specialty": "Pilates",
            "email": "trainer@example.com",
            "phone": "",
            "password": "secret9",
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert b"Trainer created" in response.data
    trainer = db.session.scalar(
        select(Trainer).where(Trainer.email == "trainer@example.com")
    )
    assert trainer is not None
    assert trainer.first_name == "Test"
    assert trainer.last_name == "Trainer"
    assert trainer.full_name == "Test Trainer"
    trainer_user = db.session.scalar(
        select(User).where(User.email == "trainer@example.com")
    )
    assert trainer_user.role == "trainer"
    assert trainer_user.check_password("secret9")


def test_trainer_can_manage_own_schedule_and_view_participants(app):
    seed_demo_data()
    client = app.test_client()

    response = login(client, "maya@fitness.local")
    assert b"TRAINER PORTAL" in response.data
    assert b"Maya Cohen" in response.data
    assert client.get("/manager/trainers").status_code == 403

    starts_at = (datetime.now() + timedelta(days=8)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    response = client.post(
        "/trainer/sessions/new",
        data={
            "title": "Beginner Mobility",
            "starts_at": starts_at.isoformat(timespec="minutes"),
            "duration_minutes": "45",
            "max_capacity": "10",
        },
        follow_redirects=True,
    )
    assert b"Workout added to the weekly schedule" in response.data
    workout = db.session.scalar(
        select(WorkoutSession).where(WorkoutSession.title == "Beginner Mobility")
    )
    assert workout.title == "Beginner Mobility"
    participants = client.get(f"/trainer/sessions/{workout.id}/participants")
    assert participants.status_code == 200
    assert b"PARTICIPANT LIST" in participants.data
