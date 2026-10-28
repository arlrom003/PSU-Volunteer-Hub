# Password recovery verification

Date: 28 October 2026. Local implementation; no deployment or live inbox delivery.

## Behavior

- Forgot password sends a random temporary password to the active user's saved email.
- Sign in with the registered email or ID and temporary password opens only the
  new-password form. Full authentication requires the new permanent password.
- Temporary passwords expire in 30 minutes. A newer successful request revokes
  previous recovery credentials and recovery sessions. A completed reset consumes
  the credential and revokes other pending resets and existing login sessions.
- Only a hash of the recovery credential is stored. The credential is absent
  from the sign-in response, recovery session cookie, and delivery error logs.
- Delivery failure rolls back recovery changes and preserves the current password
  and previous usable recovery credential. Public feedback does not reveal accounts.
- Existing reset links remain supported. The existing token table needs no migration.

## Automated checks

- `tests/test_password_recovery.py`: all 16 new cases passed as part of the run below.
- Recovery, authentication UI, and idle-session tests: 51 Python cases passed.
  The two Python wrappers for Node tests encountered Windows `spawn EPERM`.
- `TestAuth`, `TestLoginReturnDestinations`, and `TestSecurityAuditRegressions`
  in `tests/test_app.py`: 48 passed.
- Production startup and form-submit-state structure: 8 passed. The Node wrapper
  encountered the same `spawn EPERM` restriction.
- Ran the three underlying JavaScript suites using
  `node --test --test-isolation=none tests/auth-forms.test.cjs tests/session-idle.test.cjs tests/form-submit-state.test.cjs`:
  all 19 passed. This avoids spawning a separate runner process.
- `git diff --check`: passed.

## UI delivery gate

Design read: account recovery for PSU volunteers and staff, retaining the existing
university form language. ENERGY 1 / RHYTHM 1 / MOTION 1.

- Hard Gate PASS: real form actions, server-rendered CSRF, inline errors, an error
  summary, existing submit busy states, no new decorative assets or claims.
- Purpose Gate PASS: PSU blue/gold and the existing logo maintain university identity;
  existing Inter typography and spacing keep recovery consistent with sign-in.
  A single primary action directs the account-recovery task.
- Liveliness PASS: established PSU branding remains the identity motif; the primary
  form is the focal point, with existing structural whitespace and gold brand accent.
- Craftsmanship PASS: browser request/feedback exercised against isolated SQLite;
  password visibility toggles and keyboard focus checked; backend reset and replay
  behavior exercised by automated tests.
- Mobile PASS: both forms have zero document overflow at 320px and 375px; measured
  form inputs and visibility buttons are 48px high, submit buttons 46px, return
  links 44px. Desktop and mobile screenshots inspected. Viewport override reset.
- Contrast PASS: blue/white 9.97:1, secondary text/white 9.31:1, error text/white
  6.46:1. Input boundary/white 4.26:1 exceeds the 3:1 non-text requirement.
  Keyboard focus uses a visible 3px PSU-blue outline.
- Web Interface Guidelines PASS: fetched the current Vercel guidelines and reviewed
  `templates/auth/forgot_password.html` and `templates/auth/reset_password.html`.
  Shared field macros provide labels, autocomplete, email spelling settings,
  field-linked errors and password visibility controls. No in-scope findings remain.

## Remaining external verification

The selected provider is now Brevo's HTTPS API for Railway. Set `MAIL_PROVIDER=brevo`,
`BREVO_API_KEY`, `MAIL_DEFAULT_SENDER` and `MAIL_SUPPRESS_SEND=false` privately in the
app service's Railway variables. The sender must be verified in Brevo. Redeploy
the updated code and verify a real inbox round trip. No Brevo account, sender,
API key, Railway variable or deployment was created by these local checks.

Follow-up provider checks: all 10 cases in `tests/test_brevo_email.py` passed,
along with the original 16 recovery cases. Two additional recovery integration
cases passed, confirming that a Brevo HTTP 201 response persists the recovery
credential while an HTTP 401 response rolls it back. HTTPS calls were mocked.
The API connection uses Python's standard-library HTTPS client, normal certificate
validation and the existing 15-second delivery timeout. No SDK was added.

Provider activation, sender authentication, hosting egress, spam filtering and
mobile on-screen-keyboard behavior were not verified. Full-device zoom and
assistive-technology testing were not performed.
