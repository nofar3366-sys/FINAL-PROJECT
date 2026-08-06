# Fitness Studio Documentation

These documents connect the course brief in [`final2026.pdf`](../final2026.pdf)
to the implemented Flask, Jinja, Bootstrap 5, and Flask-SQLAlchemy fitness-studio
system.

## Core documents
- [Agent guide](agent.md): implementation rules and definition of done
- [Implementation plan](plan.md): scope, phases, and delivery order
- [Architecture](architecture.md): MVC boundaries, Flask structure, database modes, deployment, and security
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

## Implemented scope
The system uses three authenticated roles: Manager, Member (trainee), and
Trainer (coach). Trainers manage only their own workout slots and participant
lists. Flask-SQLAlchemy supports SQLite for local development and isolated tests,
and Supabase PostgreSQL for production on Vercel. Bonus work includes Groq
RAG/AI scheduling and allow-listed runtime Python Skills; Resend provides receipt
delivery. External AI and email integrations have demo-safe fallbacks.

The runtime Python tools in [`skills/`](../skills/) are application capabilities.
Project-scoped Cursor workflow skills live separately in
[`../.cursor/skills/`](../.cursor/skills/).

## Document precedence
If documents conflict:
1. The course brief in `final2026.pdf` for assessment requirements
2. The current code for implemented behavior
3. `requirements.md` and feature acceptance criteria for documented intent
4. `architecture.md`, `data_model.md`, and `plan.md` for design context

Update the affected design document whenever a business rule changes so the documentation and implementation remain aligned.
