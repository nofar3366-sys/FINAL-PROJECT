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
- Authenticates with a trainer account linked one-to-one to a trainer profile.
- Views only their own dashboard, sessions, and registered participants.
- Creates and cancels only sessions assigned to their own profile.

## Functional requirements
- **FR-01:** The system authenticates manager, member, and trainer users by email and password.
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
- **FR-15:** Trainers can manage their own workout slots and view participants
  without accessing another trainer's portal.
- **FR-16:** Members can use the RAG assistant and its explicitly authorized
  class-availability runtime skill.
- **FR-17:** Managers can use AI-assisted recurring scheduling after normal
  manager authorization and server-side validation.
- **FR-18:** Membership purchase/renewal records a receipt result and uses Resend
  when configured.

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
- **NFR-03 Security:** Hashed passwords, CSRF, controller role/ownership checks, ORM-safe queries, and safe cookies.
- **NFR-04 Usability:** Clean responsive Bootstrap 5 UI with clear feedback.
- **NFR-05 Accessibility:** Labels, focus visibility, keyboard access, semantic headings, and adequate contrast.
- **NFR-06 Performance:** Use bounded dashboard queries, searchable manager
  lists, eager loading, and indexes for common foreign-key/date/status lookups.
- **NFR-07 Testability:** Services accept controllable current time and use isolated test databases.
- **NFR-08 Recoverability:** Failed transactions roll back without partial balance, booking, or renewal changes.

## PDF alignment
The implemented system exceeds the minimum of two login-distinguished user
types by providing three authenticated roles. Each role has multiple user
workflows, and the organization has multiple automated business processes such
as capacity-safe booking, membership lifecycle handling, schedule cancellation,
and receipt processing. It uses HTML/CSS, Flask/Jinja server rendering, a 3NF
relational model, and MVC separation.

The implemented bonus items are Groq-backed RAG/AI assistance, Supabase
PostgreSQL as the production cloud database, and allow-listed runtime Python
Skills. Vercel hosts the application and Resend supplies receipt delivery. These
are project implementation choices that satisfy or support the brief; the brief
does not mandate the repository's exact filenames. The brief names Ollama for
the AI bonus, while this implementation deliberately substitutes Groq and must
describe that provider difference accurately during assessment.
