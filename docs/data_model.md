# Data Model

## Entity relationships
```mermaid
erDiagram
    USERS ||--o| MEMBERS : "owns login"
    TRAINERS ||--o{ WORKOUT_SESSIONS : leads
    MEMBERS ||--o{ BOOKINGS : makes
    WORKOUT_SESSIONS ||--o{ BOOKINGS : receives
    MEMBERS ||--o{ MEMBERSHIP_RENEWALS : has
    USERS ||--o{ MEMBERSHIP_RENEWALS : processed_by
    USERS ||--o{ AUDIT_LOGS : performs

    USERS {
        integer id PK
        text email UK
        text password_hash
        text role
        integer is_active
        text created_at
    }
    MEMBERS {
        integer id PK
        integer user_id FK
        text full_name
        text phone
        text membership_expires_on
        integer credit_balance
        text status
        text created_at
        text updated_at
    }
    TRAINERS {
        integer id PK
        text full_name
        text specialty
        text phone
        text email
        integer is_active
        text created_at
        text updated_at
    }
    WORKOUT_SESSIONS {
        integer id PK
        integer trainer_id FK
        text title
        text starts_at
        integer duration_minutes
        integer max_capacity
        text status
        text created_at
        text updated_at
    }
    BOOKINGS {
        integer id PK
        integer member_id FK
        integer workout_session_id FK
        text status
        integer credit_consumed
        integer credit_refunded
        text booked_at
        text cancelled_at
    }
    MEMBERSHIP_RENEWALS {
        integer id PK
        integer member_id FK
        integer processed_by_user_id FK
        text previous_expiry
        text new_expiry
        integer credits_added
        text notes
        text created_at
    }
    AUDIT_LOGS {
        integer id PK
        integer actor_user_id FK
        text action
        text entity_type
        integer entity_id
        text details_json
        text created_at
    }
```

## Table constraints
### users
- `email` uses normalized lowercase values and is unique.
- `role IN ('manager', 'member')`.
- `is_active IN (0, 1)`.

### members
- `user_id` is unique and required for member login.
- `credit_balance >= 0`.
- `status IN ('active', 'inactive')`.
- Membership validity is derived from status and expiry rather than storing a second potentially inconsistent boolean.

### trainers
- `is_active IN (0, 1)`.
- Deactivation is preferred once referenced by a session.

### workout_sessions
- `duration_minutes > 0`.
- `max_capacity > 0`.
- `status IN ('scheduled', 'cancelled', 'completed')`.
- Add an index on `(status, starts_at)` and on `trainer_id`.

### bookings
- `status IN ('booked', 'cancelled')`.
- `credit_consumed IN (0, 1)`.
- `credit_refunded IN (0, 1)` and cannot be true unless the booking is cancelled and consumed a credit.
- A unique constraint on `(member_id, workout_session_id)` keeps one lifecycle record per member/session and prevents duplicate bookings. Rebooking can reactivate the same row transactionally if that behavior is approved; the simpler first release can disallow rebooking after cancellation.
- Add indexes on `workout_session_id, status` and `member_id, status`.

### membership_renewals
- `credits_added >= 0`.
- Rows are append-only audit/history records.
- Previous and new expiry values make renewal effects explainable.

## 3NF rationale
Each table represents one subject. User credentials are separated from member business data; trainer details are not repeated on sessions; member/session details are not repeated on bookings; renewal facts are stored as history rather than repeating member attributes. Non-key attributes depend on the key, the whole key, and nothing but the key.

## Derived values
Do not persist values that can drift:
- Active booking count: count booked rows for a session.
- Remaining capacity: session capacity minus active booking count.
- Membership active: active member/account and expiry on or after the applicable current date.
- Session bookable: scheduled, future, remaining capacity positive, and member eligible.

## Transaction boundaries
- **Book:** lock write access, re-read member/session/count, validate, insert booking, decrement credit, commit.
- **Cancel booking:** lock write access, validate active booking and policy, cancel row, increment credit once, commit.
- **Renew membership:** lock write access, insert renewal history, update expiry/credits/status, commit.
- **Cancel session:** update status and process any required booking/credit effects under one explicit policy and transaction.
