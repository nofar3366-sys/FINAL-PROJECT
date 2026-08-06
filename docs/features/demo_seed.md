# Feature: Database Initialization and Demo Seed

## Purpose
Provide a fast, deterministic way to create the configured relational schema
and populate realistic demonstration data for assessment. Local setup normally
uses SQLite; production schema provisioning targets Supabase PostgreSQL before
Vercel deployment.

## Commands
- `flask --app app init-db` creates the schema on a fresh configured database.
- `flask --app app seed-demo` inserts demonstration records.

The seed command should refuse to run when business data already exists unless an explicit development-only reset workflow is invoked.

## Seed contents
- One active manager account
- At least three trainers with distinct specialties and linked demo logins where
  the presentation requires trainer authentication
- At least four members:
  - active with credits;
  - active with zero credits;
  - expired;
  - inactive
- Multiple upcoming sessions:
  - open capacity;
  - nearly full;
  - full;
  - cancelled
- A small set of active/cancelled bookings
- Renewal-history examples

Use dates relative to the seed execution date so upcoming sessions remain demonstrable. Keep names fictional and clearly non-production.

## Credentials
Development credentials may be printed after seeding and documented in setup instructions. Passwords still pass through the same hashing code used by normal account creation and are never stored in plaintext.

## MVC and ownership
- Schema and seed data builders belong to the persistence setup layer and use
  Flask-SQLAlchemy models/services.
- CLI registration belongs to application initialization.
- Seeding must reuse model/service validation where practical, without issuing HTTP requests.

## Acceptance criteria
- Initialization succeeds on an empty database and enables all constraints/indexes.
- Seed succeeds once and produces every required demonstration state.
- Seeded users can authenticate with documented development credentials.
- Re-running seed does not silently duplicate or overwrite records.
- Automated tests use separate fixture data and never depend on the development database.
