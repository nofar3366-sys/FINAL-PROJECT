# Testing Strategy

## Test layers
### Unit and model tests
- Password hashing and verification
- Date/status eligibility calculations
- Input normalization and validation
- CRUD repository behavior and constraint mapping

### Service transaction tests
- Successful booking decrements one credit.
- Full session produces no booking and no credit change.
- Zero-credit or expired member produces no booking.
- Duplicate booking produces no second credit charge.
- Cancellation restores one credit exactly once.
- Failed renewal leaves expiry, credits, and history unchanged.
- Session capacity cannot be reduced below active bookings.

### Controller tests
- Anonymous requests redirect to login.
- Manager pages reject members with 403.
- Member pages reject managers where member context is required.
- A member cannot view or mutate another member's records.
- State changes require POST and valid CSRF data when enabled.
- Forms display validation errors and preserve safe input.
- Successful POST requests follow Post/Redirect/Get.

### End-to-end smoke tests
- Manager logs in, creates member/trainer/session, and renews membership.
- Member logs in, books an eligible session, sees updated balance, and cancels.
- Responsive navigation and critical forms work at common viewport sizes.

## Strict capacity test
Create a session with one remaining place and two eligible members. Start two separate database connections/requests that attempt to book it. Assert:
- exactly one request succeeds;
- exactly one active booking is created;
- active bookings never exceed capacity;
- only the successful member loses a credit;
- the unsuccessful member receives a clear capacity conflict.

SQLite's locking may serialize the requests rather than run statements simultaneously; the test still verifies the transaction re-checks capacity after acquiring write access.

## Fixtures
- Temporary SQLite database per test or test function.
- Application configured for testing with a fixed secret and CSRF testing strategy.
- Fixed clock/date to avoid boundary flakiness.
- Factories for manager, active/expired member, trainer, scheduled/full/cancelled session, renewal, and booking.

## Manual acceptance checklist
- Keyboard-only login, navigation, form submission, booking, and cancellation.
- Small-screen layout at approximately 375 px width.
- Clear status and error text without relying only on badge color.
- Browser refresh after POST does not repeat mutations.
- Direct URL attempts cannot bypass role checks.
- Seed command initializes a convincing demo in one step.

## Quality gate
Before demonstration:
1. Initialize a clean database.
2. Run the full automated suite.
3. Run the seed command.
4. Complete both role walkthroughs.
5. Verify no plaintext credentials, secret keys, or database files intended to be local are committed.
