# Fitness Studio Documentation

These documents translate the course brief into an implementation-ready design for a Flask, Jinja, Bootstrap 5, and SQLite fitness-studio application.

## Core documents
- [Agent guide](agent.md): implementation rules and definition of done
- [Implementation plan](plan.md): scope, phases, and delivery order
- [Architecture](architecture.md): MVC boundaries, Flask structure, SQLite transactions, and security
- [Requirements](requirements.md): actors, functional requirements, rules, and quality attributes
- [Data model](data_model.md): 3NF entities, relationships, constraints, and transaction boundaries
- [UI/UX](ui_ux.md): Bootstrap layouts, navigation, states, and accessibility
- [Testing](testing.md): automated and manual verification strategy

## Feature designs
- [User authentication](features/user_auth.md)
- [Membership management](features/membership_management.md)
- [Trainer management](features/trainer_management.md)
- [Workout session management](features/session_management.md)
- [Session booking](features/session_booking.md)
- [Database initialization and demo seed](features/demo_seed.md)

## Scope decision
The system uses three authenticated roles: Manager, Member (trainee), and Trainer (coach). Trainers manage only their own workout slots and participant lists. Approved bonus integrations include Groq RAG/AI scheduling and Resend receipts, both with demo-safe fallbacks. Local SQLite remains the authoritative database.

## Document precedence
If documents conflict:
1. Explicit user decisions and `requirements.md`
2. Feature acceptance criteria
3. `architecture.md` and `data_model.md`
4. Implementation details in `plan.md`

Update the affected design document whenever a business rule changes so the documentation and implementation remain aligned.
