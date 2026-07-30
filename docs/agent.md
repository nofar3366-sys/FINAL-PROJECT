# Fitness Studio Project Agent Guide

## Mission
Build an academic fitness-studio management web application from the approved documents in `docs/`. The system must demonstrate Python, Flask, Jinja, HTTP, SQL, normalized relational data, business rules, workflow automation, and a clear Model-View-Controller (MVC) structure.

## Required stack
- Python 3 and Flask
- SQLite with parameterized SQL
- Jinja templates rendered on the server
- Bootstrap 5 with small, focused custom CSS only where needed
- Flask sessions for authentication
- Werkzeug password hashing
- Pytest for automated tests

Do not introduce React, an ORM, or a cloud replacement for SQLite. The approved bonus scope is Groq RAG/AI scheduling and Resend email receipts with safe fallbacks.

## Roles
- **Manager:** full CRUD for members, trainers, and workout sessions; renews memberships; manages schedules; views operational dashboards.
- **Member:** logs in, views only their own profile, membership status, and balance; books or cancels their own bookings.
- **Trainer:** authenticated coach linked to one trainer profile; manages only their own sessions and participant lists.

Every protected request must enforce authorization in the controller. Hiding a button in a template is not authorization.

## Non-negotiable business rules
1. A member may book only when authenticated as that member.
2. The member must have an active, unexpired membership and positive session balance.
3. A booking must never exceed the session's `max_capacity`.
4. Capacity checking and booking insertion must run in one SQLite write transaction.
5. A member may not book the same session twice.
6. A member may not book a session that has started, is cancelled, or has no remaining places.
7. A successful booking consumes exactly one credit.
8. An eligible cancellation restores exactly one credit and cannot restore it twice.
9. Membership renewal must be recorded in immutable renewal history and update the member's current expiry and balance atomically.
10. Sessions with existing bookings must be cancelled rather than hard-deleted.

## MVC boundaries
- **Models** own SQL, persistence, transactions, and domain-shaped data access.
- **Controllers** parse requests, authorize users, orchestrate model operations, flash results, and redirect/render.
- **Views** are Jinja templates only; they display supplied data and do not execute SQL or contain core business rules.
- Shared domain services may coordinate multi-model operations such as booking and renewal transactions.

Controllers must not embed SQL. Models must not import Flask request or template objects. Templates must not make database calls.

## Implementation conventions
- Use an application factory and Flask blueprints.
- Keep configuration in environment-aware config classes; never commit a production secret.
- Store timestamps in SQLite in one documented format, preferably UTC ISO 8601.
- Enable SQLite foreign keys for every connection and use a busy timeout.
- Use Post/Redirect/Get after successful form submissions.
- Protect all state changes with POST; add CSRF protection before production use.
- Validate on the server even when HTML inputs also validate.
- Use descriptive snake_case names and small functions.
- Prefer soft status transitions where history matters.
- Seed data must be deterministic and safe to run on a fresh database.

## Definition of done
- Acceptance criteria in the feature documents pass.
- Manager, member, and trainer roles cannot cross authorization boundaries.
- Capacity and credit invariants hold under competing booking attempts.
- Database schema is in 3NF and foreign keys are enforced.
- A fresh setup can initialize and seed the database.
- Automated tests cover happy paths, validation, authorization, transactions, and capacity edge cases.
- The interface is responsive, keyboard-usable, and gives clear success/error feedback.
