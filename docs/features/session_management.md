# Feature: Workout Session Management

## Purpose
Allow the manager to build and maintain a safe studio schedule with trainer assignments, timing, status, and capacity.

## User stories
- As a manager, I can create, view, edit, filter, and cancel sessions.
- As a manager, I can see booking count and remaining capacity.
- As a manager, I cannot reduce capacity below active bookings.
- As a member, I can browse upcoming scheduled sessions.

## MVC design
- **Model:** session CRUD, trainer joins, booking counts, date/status filters.
- **Service:** schedule conflict, capacity-change, and cancellation policy.
- **Controller:** manager schedule routes and read-only member catalogue route.
- **View:** schedule table/cards, session form/detail, occupancy indicators.

## Suggested manager routes
- `GET /manager/sessions`
- `GET, POST /manager/sessions/new`
- `GET /manager/sessions/<id>`
- `GET, POST /manager/sessions/<id>/edit`
- `POST /manager/sessions/<id>/cancel`

## Rules and validation
- Title, active trainer, future start, positive duration, and positive integer capacity are required.
- End time is derived from start plus duration.
- A trainer cannot be assigned to overlapping scheduled sessions.
- Capacity cannot be set below current active booking count.
- Started/completed sessions cannot be edited as future schedule items.
- Sessions with bookings are cancelled rather than deleted.
- Cancellation behavior must be explicit: cancel active bookings and restore each consumed credit once in the same transaction.

## Session cancellation transaction
1. Acquire SQLite write transaction.
2. Re-read scheduled session and active bookings.
3. Mark session cancelled.
4. Mark each active booking cancelled with timestamp.
5. Restore credits only where `credit_consumed = 1 AND credit_refunded = 0`, then set `credit_refunded = 1`.
6. Write audit information and commit.

## Acceptance criteria
- Only managers mutate sessions.
- Invalid dates, duration, trainer, or capacity are rejected.
- Remaining capacity equals capacity minus active bookings.
- Competing edits cannot lower capacity beneath bookings.
- Session cancellation leaves no active bookings and refunds each affected member once.
- Members cannot book cancelled, full, or started sessions.
