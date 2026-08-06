# Fitness Studio Management System

Academic final project for a web information-systems course. The application manages members, trainers, memberships, workout sessions, bookings, capacity, reporting, and selected AI/cloud bonus integrations.

## Technology and Architecture
- Python 3, Flask, Flask-SQLAlchemy, Jinja2, and Bootstrap 5
- Local SQLite database at `instance/fitness_studio.db`
- MVC organization:
  - Models: [`models/`](models/)
  - Controllers and Flask Blueprints: [`controllers/`](controllers/)
  - Views: [`fitness_studio/templates/`](fitness_studio/templates/)
  - Business/integration services: [`services/`](services/)
- Application factory: [`fitness_studio/__init__.py`](fitness_studio/__init__.py)

SQLite remains the default local database when `DATABASE_URL` is unset. For production and Vercel, set `DATABASE_URL` to your Supabase **Transaction pooler** URI (port **6543**), not the direct `5432` connection. Groq and Resend are optional integrations and do not replace the relational database.

## User Roles
### Manager
The `manager` role is enforced by `manager_required` in [`controllers/auth.py`](controllers/auth.py). Managers can maintain members and trainers, schedule or cancel classes, manage subscriptions, view analytics, and export CSV reports.

### Member
The `member` role (the trainee/regular-user role) can access only its linked `Member` record. Members can view the weekly calendar, book/cancel their own classes, purchase demo membership plans, and use the AI assistant.

### Trainer
The `trainer` role is linked one-to-one to a `Trainer` profile. `trainer_required` limits coaches to their own portal, where they can add and cancel their own workout slots and view registered participants.

Demo manager credentials:
```text
manager@fitness.local
Demo123!
```

Demo trainer credentials: `maya@fitness.local` / `Demo123!`.

## Required User Workflows
### Member workflows
1. **Class booking and cancellation:** [`controllers/member.py`](controllers/member.py), [`services/booking_service.py`](services/booking_service.py), and [`schedule.html`](fitness_studio/templates/member/schedule.html). Booking consumes one credit; eligible cancellation refunds it once.
2. **Membership purchase and renewal:** [`services/membership_service.py`](services/membership_service.py) and [`renewal.html`](fitness_studio/templates/member/renewal.html). Demo checkout activates/extends membership, adds credits, records history, and processes a receipt.

The member also has a personal overview and upcoming-workout dashboard at `/member/dashboard`.

### Manager workflows
1. **Member/trainer/subscription administration:** manager routes in [`controllers/manager.py`](controllers/manager.py) provide create, view, edit, activate, suspend, and cancel operations.
2. **Scheduling and operational reporting:** managers manually or AI-schedule sessions, cancel sessions with automatic refunds, review dashboard analytics, and export attendance/revenue CSV reports.

### Trainer workflows
1. **Own-slot management:** trainers add workouts to the weekly calendar and cancel only sessions assigned to their profile.
2. **Participant review:** trainers open each owned workout to view its current registered trainees.

## Organizational Business Processes
1. **Capacity and overbooking control:** [`services/booking_service.py`](services/booking_service.py) uses a database transaction, rechecks active booking count, blocks full classes, and updates credits atomically. The implementation uses SQLite write locking locally and database row locking where supported by PostgreSQL.
2. **Membership lifecycle enforcement:** the same service verifies account status, subscription status, expiration date, and positive credit balance before every booking. [`services/membership_service.py`](services/membership_service.py) applies purchases and renewals atomically.

Session cancellation with bulk credit refunds is enforced in [`services/scheduling_service.py`](services/scheduling_service.py).

## Third Normal Form (3NF)
The database separates independent subjects into dedicated tables:
- `users` stores authentication and role data.
- `members` and `trainers` store role-specific business data.
- `workout_sessions` references trainers instead of repeating trainer details.
- `bookings` is the member/session relationship and prevents duplicate bookings.
- `membership_plans` stores reusable plan definitions.
- `membership_purchases`, `membership_renewals`, and `membership_subscriptions` store separate transaction/history/current-status facts.
- `audit_logs` stores manager/system actions.

Every non-key attribute describes its table's key; plan, trainer, user, and session attributes are referenced through foreign keys rather than duplicated. Names are stored as atomic `first_name` and `last_name` columns (1NF); `full_name` is a derived Python property only. Foreign keys are enabled on every SQLite connection, and derived values such as remaining capacity are calculated from normalized records.

## Three Bonus Items
### Bonus 1: RAG AI Assistant
[`services/ai_service.py`](services/ai_service.py) retrieves relevant policy/schedule context and sends it to Groq using `llama-3.3-70b-versatile`. `GROQ_API_KEY` is read from the environment. If the key is absent or Groq fails, a deterministic local RAG response keeps the live demo operational.

The member interface is available at `/member/assistant`. It includes a personalized Workout Recommendation Agent that combines the member's status/history/goal with bookable classes from the configured database. Manager natural-language scheduling uses the same provider with a local parsing fallback.

The course brief names Ollama for this bonus; this project implements the same
AI-server and RAG pattern with Groq as the provider. This provider substitution
should be stated clearly during the presentation.

### Bonus 2: Cloud Database (Supabase DBaaS)
Production persistence uses **PostgreSQL on Supabase** via `DATABASE_URL` (Transaction pooler, port 6543). The Flask app on Vercel is the application tier; Supabase is the managed data tier. Local pytest continues to use ephemeral SQLite.

### Bonus 3: Explicit AI Skills
The allow-listed tools are defined in [`skills/`](skills/) and registered in [`skills/registry.py`](skills/registry.py):
- `get_class_availability_skill(date, specialty)` queries live capacity from the configured database.
- `schedule_class_skill(trainer_id, date_time, capacity)` creates a validated class for an authorized manager.
- Additional member-status and recurring-scheduling skills support the AI workflows.

The AI page visibly demonstrates policy RAG and direct availability-skill execution.

## Email Receipt Integration
Set `RESEND_API_KEY` to send real purchase receipts through Resend. Without a key, [`services/email_service.py`](services/email_service.py) logs a professional mock receipt so checkout remains reliable.

## Setup and Run
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m flask --app app init-db
.\venv\Scripts\python.exe -m flask --app app seed-demo
.\venv\Scripts\python.exe -m flask --app app run --debug
```

For a database created before trainer login support, run `flask --app app upgrade-db` once instead of deleting existing data.

Vercel deploys `app.py` as the single WSGI entrypoint.

Optional environment variables:
```powershell
$env:GROQ_API_KEY = "your-key"
$env:RESEND_API_KEY = "your-key"
$env:DATABASE_URL = "postgresql://postgres.YOUR_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
```

## Verification
```powershell
.\venv\Scripts\python.exe -m pytest -q
```
