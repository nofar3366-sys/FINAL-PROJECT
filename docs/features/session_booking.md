# Feature: Session Booking

## Purpose
Let members book and cancel their own workout sessions while strictly protecting membership eligibility, credit balances, duplicate prevention, and maximum capacity.

## User stories
- As a member, I can see which upcoming sessions I am eligible to book.
- As an eligible member, I can book a session with space.
- As a member, I can see my upcoming and historical bookings.
- As a member, I can cancel an eligible future booking and recover its credit.

## Booking eligibility
At transaction time all conditions must be true:
- authenticated account and member are active;
- membership has not expired;
- credit balance is greater than zero;
- session is scheduled and has not started;
- active booking count is lower than `max_capacity`;
- member has no existing booking for the session.

## Atomic booking algorithm
```text
BEGIN IMMEDIATE
  re-read member and session
  count active bookings
  validate every eligibility rule
  insert booking with credit_consumed = 1 and credit_refunded = 0
  update member set credit_balance = credit_balance - 1
    where id = ? and credit_balance > 0
  verify exactly one member row changed
COMMIT
```

On any validation, constraint, or update failure, roll back. The controller displays a specific safe message and must not retry a non-idempotent operation blindly.

## Cancellation policy
Default first-release policy: a member may cancel a booked session only before it starts. Cancellation and one-credit restoration occur in one immediate transaction. The refund update is conditional on `credit_consumed = 1 AND credit_refunded = 0` and sets `credit_refunded = 1`, so repeating the request cannot restore another credit.

## MVC design
- **Model:** session availability queries, booking/history queries, constrained updates.
- **Service:** booking and cancellation transactions plus domain errors.
- **Controller:** member-only session catalogue, book, booking list, and cancel.
- **View:** availability cards/table, booking status, disabled actions with reasons.

## Suggested member routes
- `GET /member/sessions`
- `POST /member/sessions/<id>/book`
- `GET /member/bookings`
- `POST /member/bookings/<id>/cancel`

The member identity always comes from the authenticated session, never from a posted member ID.

## Capacity enforcement
The displayed remaining count is informational and may become stale. The authoritative check occurs after acquiring SQLite write access. A unique booking constraint and non-negative credit check provide final database safeguards.

## Acceptance criteria
- Eligible booking creates one booking and consumes one credit.
- A full session is never oversubscribed under competing requests.
- Ineligible or duplicate attempts change neither bookings nor credits.
- A member cannot book/cancel for another member by changing URL/form data.
- Valid cancellation changes booking status and restores exactly one credit.
- Repeated cancellation is safe and does not add credits.
- UI clearly distinguishes full, already-booked, expired, zero-credit, cancelled, and started states.
