# Feature: User Authentication and Authorization

## Purpose
Authenticate manager and member users and enforce role-based access at every protected controller.

## User stories
- As a manager, I can log in and access management functions.
- As a member, I can log in and access only my own dashboard, sessions, and bookings.
- As any user, I can log out and invalidate my session.
- As an inactive user, I cannot authenticate.

## Workflow
1. User submits normalized email and password.
2. Controller looks up the active user by email.
3. Werkzeug verifies the stored password hash.
4. On success, old session data is cleared and minimal identity data is stored.
5. On each protected request, the current user is loaded and role checked.
6. Logout clears session data and redirects to login.

## MVC design
- **Model:** user lookup, active-state check, password hash storage.
- **Controller:** `/login`, `/logout`, current-user loading, `login_required`, and `role_required`.
- **View:** shared login form and safe error message that does not reveal whether an email exists.

## Suggested routes
- `GET, POST /auth/login`
- `POST /auth/logout`

After login, accept only validated local redirect targets; otherwise route managers to the manager dashboard and members to their own dashboard.

## Validation and security
- Email is required, trimmed, and normalized.
- Password is required and never logged.
- Passwords are hashed with Werkzeug defaults.
- Session secret comes from configuration/environment.
- Cookies use `HttpOnly`, `SameSite=Lax`, and `Secure` in HTTPS deployments.
- Add CSRF protection to login and logout forms.
- Optional rate limiting can be added later; generic errors are required now.

## Acceptance criteria
- Correct active credentials establish the expected role session.
- Invalid or inactive credentials do not authenticate.
- Anonymous access to protected routes redirects to login.
- Authenticated wrong-role access returns 403.
- A member cannot substitute an ID to access another member.
- Logout removes access to protected pages.
