# Feature: Membership Management

## Purpose
Allow the manager to maintain member records and renew memberships while preserving a reliable history of expiry and credit changes.

## User stories
- As a manager, I can create and update a member.
- As a manager, I can activate/deactivate a member without deleting history.
- As a manager, I can renew a membership and add session credits.
- As a manager, I can see renewal history and members nearing expiry.
- As a member, I can see my own status, expiry, and balance.

## Manager workflow
1. Open a member record.
2. Review current expiry, balance, status, and renewal history.
3. Choose a new expiry and non-negative credits to add.
4. Submit renewal.
5. In one transaction, validate, append a renewal record, update member expiry/balance/status, and write an audit event.
6. Redirect to the detail page with a summary.

## MVC design
- **Model:** member CRUD queries, expiry filters, renewal history, constraints.
- **Service:** atomic renewal and status transition rules.
- **Controller:** manager list/detail/forms/renewal and member self-view.
- **View:** member table, form, detail, renewal form/history, member status card.

## Suggested manager routes
- `GET /manager/members`
- `GET, POST /manager/members/new`
- `GET /manager/members/<id>`
- `GET, POST /manager/members/<id>/edit`
- `POST /manager/members/<id>/deactivate`
- `GET, POST /manager/members/<id>/renew`

## Validation
- Unique normalized account email.
- Required full name and valid contact lengths.
- Expiry is a valid date and follows the chosen renewal policy.
- Credits added is an integer greater than or equal to zero.
- Resulting credit balance cannot exceed any documented operational maximum.
- Deactivated members cannot log in or book.

## Renewal policy
Default first-release policy: the manager explicitly selects the new expiry date and credits to add. The new expiry must be later than the current effective expiry. Renewal never silently removes unused credits.

## Acceptance criteria
- Creation produces linked user/member records without plaintext password storage.
- Editing does not alter renewal history.
- Renewal creates one history row and updates expiry/credits atomically.
- Invalid renewal creates no history and changes no balance/expiry.
- Member can view only their own status and balance.
- Expired, inactive, or zero-credit members receive the correct booking restriction.
