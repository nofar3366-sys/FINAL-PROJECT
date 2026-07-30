# Feature: Trainer Management

## Purpose
Let the manager maintain trainer profiles and login accounts. Authenticated trainers can manage only their own workout sessions and view their participants.

## User stories
- As a manager, I can create, view, edit, and deactivate trainers.
- As a manager, I can search trainers by name or specialty.
- As a manager, I can see a trainer's upcoming sessions.
- As a manager, I can assign only an active trainer to a new session.

## MVC design
- **Model:** trainer CRUD, active filter, search, session relationship queries.
- **Controller:** manager-only list, create, detail, edit, and deactivate actions.
- **View:** responsive trainer list, form, detail, status badge, upcoming schedule.

## Suggested routes
- `GET /manager/trainers`
- `GET, POST /manager/trainers/new`
- `GET /manager/trainers/<id>`
- `GET, POST /manager/trainers/<id>/edit`
- `POST /manager/trainers/<id>/deactivate`

## Validation and rules
- Full name and specialty are required.
- Email, when supplied, is normalized and syntactically valid.
- Phone is validated for reasonable length/characters.
- Referenced trainers are deactivated, not hard-deleted.
- Existing sessions retain their trainer relationship after deactivation.
- Deactivated trainers cannot be selected for newly created sessions.
- Changing a future session to another trainer is handled by session management and must check conflicts.

## Acceptance criteria
- Manager can complete trainer CRUD/status workflows.
- Members cannot access trainer management routes.
- Invalid data is rejected with field-level feedback.
- Deactivation preserves historical and upcoming session records.
- Trainer detail shows an accurate upcoming schedule.
