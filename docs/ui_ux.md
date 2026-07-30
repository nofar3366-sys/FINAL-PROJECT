# UI and UX Design

## Design direction
Use a simple, clean, responsive Bootstrap 5 interface. Favor familiar navigation, readable tables/cards, clear statuses, and explicit actions over custom visual complexity.

## Shared layout
- Responsive navbar with product name, role-appropriate links, signed-in identity, and logout.
- Flash-message region announced to assistive technology.
- Main content container with page heading and optional primary action.
- Consistent badges for active, expired, scheduled, full, cancelled, and low-credit states.
- Confirmation modal or dedicated confirmation page for destructive/cancellation actions.

## Manager navigation
- Dashboard
- Members
- Trainers
- Sessions
- Logout

The manager dashboard should highlight active members, expiring memberships, upcoming sessions, full/nearly-full sessions, and quick links to common workflows.

## Member navigation
- My Dashboard
- Available Sessions
- My Bookings
- Logout

The member dashboard should make expiry and remaining credits immediately visible, warn about blocked booking reasons, and list upcoming bookings.

## Screen behavior
- Desktop lists use Bootstrap tables; narrow screens may use responsive table wrappers or cards.
- Forms retain submitted values after validation failure and show field-level errors.
- Empty states explain what happened and offer an appropriate next action.
- Booking buttons display the actionable state: `Book`, `Full`, `Membership expired`, `No credits`, `Already booked`, or `Started`.
- Dates are displayed in the studio's documented local timezone and unambiguous format.
- Pagination and filters preserve query parameters.

## Accessibility
- Every input has a programmatic label.
- Do not rely on color alone for status.
- Maintain logical heading order and visible keyboard focus.
- Buttons and links use action-specific text.
- Validation summary links to invalid fields where practical.
- Modals, if used, must support focus management; a normal confirmation page is an acceptable simpler alternative.

## Key templates
```text
templates/
  base.html
  components/
    flashes.html
    pagination.html
    status_badge.html
  auth/login.html
  manager/dashboard.html
  manager/members/{index,form,detail,renew}.html
  manager/trainers/{index,form,detail}.html
  manager/sessions/{index,form,detail}.html
  member/dashboard.html
  member/sessions/index.html
  member/bookings/index.html
  errors/{403,404,409,500}.html
```

## Feedback language
Messages should explain both outcome and next step:
- “Booking confirmed. One credit was used.”
- “This session became full before your booking completed. Choose another session.”
- “Membership renewed through 31 December 2026; 10 credits were added.”
- “You cannot book because your membership has expired. Contact the studio manager.”
