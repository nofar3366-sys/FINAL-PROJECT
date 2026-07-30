# Fitness Studio Implementation Plan

## Goal
Deliver a Flask and SQLite web application that lets a manager administer members, trainers, memberships, and workout sessions while members securely view their account and book sessions under strict credit and capacity rules.

## Scope
### Included
- Manager and member login/logout
- Role-based access control
- Member, trainer, and workout-session management
- Membership renewal with credit allocation and renewal history
- Member self-service dashboard
- Session booking and cancellation
- Strict transactional capacity enforcement
- Responsive Bootstrap 5/Jinja interface
- Fresh database initialization and demonstration seed data
- Automated model, service, controller, and authorization tests
- Groq-powered RAG assistant with a safe local fallback
- AI-assisted recurring scheduling and Resend receipt integration

### Excluded for the first release
- Trainer login
- Online payment processing
- Waitlists and SMS notifications
- External or cloud replacement for the local SQLite database

## Delivery phases
1. **Foundation**
   - Create the Flask application factory, configuration, blueprints, base templates, database connection lifecycle, schema initialization, and CLI seed command.
2. **Identity and authorization**
   - Implement hashed credentials, login/logout, role decorators, session security, and manager/member route boundaries.
3. **Manager workflows**
   - Add member and trainer CRUD, session scheduling, validation, dashboards, and safe status transitions.
4. **Membership workflow**
   - Add renewal plans/history and an atomic renewal transaction that updates expiry and credits.
5. **Member self-service**
   - Add member dashboard, available-session listing, transactional booking, cancellation, and clear availability states.
6. **Quality and demonstration**
   - Add test fixtures, concurrency/capacity tests, accessibility and responsive checks, setup instructions, and deterministic seed data.

## Recommended implementation order
1. Schema and model primitives
2. Authentication
3. Manager member/trainer management
4. Session scheduling
5. Membership renewal
6. Booking and cancellation service
7. Dashboards and UI polish
8. End-to-end verification

## Demonstration seed
- One manager account with a documented development-only password
- Several trainers with different specialties
- Several members covering active, expired, and zero-credit states
- Upcoming sessions covering available, full, and cancelled states
- A small set of bookings and renewal-history records

The seed command must clearly label credentials as development data and must not silently overwrite an existing populated database.

## Completion checklist
- Fresh clone setup is reproducible.
- Manager can complete every required CRUD and renewal workflow.
- Member can see only their own data and manage only their own bookings.
- Booking cannot oversubscribe a session or produce a negative credit balance.
- All state-changing routes reject unauthorized and invalid requests.
- Key acceptance criteria in `docs/features/` are automated.
- Documentation and code consistently reflect MVC.
