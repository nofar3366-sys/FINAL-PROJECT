# Requirements

## Actors
### Manager
- Authenticates with a manager account.
- Creates, views, updates, and deactivates members and trainers.
- Creates, edits, views, and cancels workout sessions.
- Renews memberships and allocates session credits.
- Reviews membership, attendance, booking, and capacity information.

### Member
- Authenticates with their own account.
- Views only their own profile, membership expiry/status, credit balance, and bookings.
- Browses eligible upcoming sessions.
- Books and cancels only their own bookings under system rules.

### Trainer
Trainer is a managed entity, not an authenticated actor in the first release.

## Functional requirements
- **FR-01:** The system authenticates manager and member users by username/email and password.
- **FR-02:** The system authorizes every protected endpoint according to role.
- **FR-03:** The manager can manage member records and account status.
- **FR-04:** The manager can manage trainer records and specialties.
- **FR-05:** The manager can schedule a session with trainer, date/time, duration, and positive capacity.
- **FR-06:** The manager can edit future sessions without invalidating existing bookings.
- **FR-07:** The manager can cancel a session and preserve its audit/history data.
- **FR-08:** The manager can renew a membership with expiry and credit changes in one transaction.
- **FR-09:** The member dashboard displays current membership and credit status.
- **FR-10:** Members can browse upcoming non-cancelled sessions and see places remaining.
- **FR-11:** An eligible member can book once into a session with remaining capacity.
- **FR-12:** A booking consumes one credit atomically.
- **FR-13:** A valid cancellation restores one credit atomically.
- **FR-14:** The system provides deterministic demonstration seed data.

## Core business rules
- Capacity is a positive integer and cannot be lower than active booking count.
- Remaining places equal `max_capacity - active_booking_count`.
- Expiry is interpreted using one documented studio timezone at the UI boundary.
- A membership is active only if the member/account is active and the expiry has not passed.
- Credit balance cannot be negative.
- Duplicate active bookings are prohibited.
- Past or started sessions cannot be booked.
- Cancelled sessions cannot be booked.
- Renewal and booking history is retained.
- Deactivation blocks login/booking but does not erase history.

## Non-functional requirements
- **NFR-01 Maintainability:** Clear MVC boundaries and feature blueprints.
- **NFR-02 Integrity:** Foreign keys, uniqueness, checks, and atomic transactions.
- **NFR-03 Security:** Hashed passwords, CSRF, role checks, parameterized SQL, safe cookies.
- **NFR-04 Usability:** Clean responsive Bootstrap 5 UI with clear feedback.
- **NFR-05 Accessibility:** Labels, focus visibility, keyboard access, semantic headings, and adequate contrast.
- **NFR-06 Performance:** Paginate manager lists; index foreign keys and common date/status lookups.
- **NFR-07 Testability:** Services accept controllable current time and use isolated test databases.
- **NFR-08 Recoverability:** Failed transactions roll back without partial balance, booking, or renewal changes.

## PDF alignment
The design provides two login-distinguished user types, at least two workflows per user, multiple organization-level business workflows, HTML/CSS presentation, Flask/Jinja server rendering, a 3NF relational database, and MVC separation. Optional bonus integrations are intentionally outside the first release.
