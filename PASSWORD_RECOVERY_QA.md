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

## Railway setup follow-up, 28 October 2026

- Published commit `659500e` to `arlrom003/PSU-Volunteer-Hub` on `main`, the source
  connected to `psu-volunteer-hub-main` in the `zonal-light` Railway project.
- The user saved `BREVO_API_KEY` in the web app service. Its value was kept masked.
- Added and applied `MAIL_PROVIDER=brevo`,
  `MAIL_DEFAULT_SENDER=23ur0679@psu.edu.ph`, and `MAIL_SUPPRESS_SEND=false`.
- Deployment `6d33e7ae-c66f-4b6b-97de-a1cd00e7eeef` became Active/Online, and the
  live forgot-password form rendered the new temporary-password instructions.
- One reset request for the user's email returned HTTP 500 before email delivery.
  Deployment logs identify `Unknown server host 'mysql.railway.internal'`.
  The linked MySQL service has no active deployment; its previous deployment
  was removed three days earlier. No password-reset email delivery was verified.
- Automatic approval review rejected confirmation of the existing MySQL
  deployment's redeploy operation because a production database restart requires
  explicit user approval. No database restart, schema change, import, restore,
  credential change or database deletion was completed.
- The unrelated pending command, coordinator and existing test changes were
  preserved locally. The existing related admin recovery-token revocation fix
  was included in the email-recovery release.

### Approved database restart and provider connectivity

- The user explicitly approved restarting the existing MySQL service. Redeploy
  of the saved configuration succeeded as deployment
  `a7afff2d-584e-4c7c-b917-66cc4d55ed8c`. No import or schema change was performed.
- The next live forgot-password request completed normally and redirected to
  sign-in. Brevo still showed zero transactional email logs.
- A read-only check in the deployed app confirmed the provider is `brevo`,
  sending is enabled, and an API key is present. No credential value was printed.
  The user's tested email was not registered in the app, and the user confirmed
  they had not created an app account yet.
- A read-only Brevo statistics request from the deployed app returned HTTP 401
  with an unauthorized source-IP error for `34.124.168.27`. The Brevo security UI
  independently lists that address under Unauthorized IP addresses. API IP
  blocking is enabled and the authorized list is empty.
- Authorization of this exact Railway IP is prepared for user approval. IP
  blocking has not been disabled, and no addresses have been authorized yet.
  Account registration and a real inbox delivery test remain outstanding.

### Approved IP authorization

- The user approved authorizing `34.124.168.27`. Brevo now lists exactly one
  authorized address, with zero unauthorized addresses, while API IP blocking
  remains enabled. The key's permissions were not changed.
- Repeating the same read-only transactional statistics request from Railway
  returned HTTP 200, confirming network access, key authentication and the
  transactional-email permission. The secret value was never printed or copied.
- The user is creating their first app account. A real temporary-password
  message, inbox receipt, sign-in with that credential and permanent-password
  replacement remain unverified until the user completes account registration.
- Railway's outbound IP may change with infrastructure or deployment changes.
  If Brevo reports another unauthorized address later, review and authorize the
  new app address before retrying; do not disable IP blocking automatically.

### Demo service setup

- Applied the Brevo provider, verified sender, API key and enabled-sending
  settings to `PSU-Volunteer-Hub-Demo`. Deployment
  `c8c023a6-37ad-47ed-878a-15a416b92b97` is running the recovery release.
- The user separately approved authorizing the demo source IP `100.48.150.79`
  and restarting `PSU Volunteer Hub Demo DB` from its saved configuration and
  attached volume. Database deployment `f5e415b1-dc95-4ddb-8e73-79a50e4f10a4`
  became Active. No import or schema change was performed.
- Brevo lists both approved app addresses, with API IP blocking still enabled.
  A read-only statistics request from the demo returned HTTP 200, and a direct
  `SELECT 1` from the demo app confirmed the database connection.
- The owner's tested email is absent from the demo users table. Its live reset
  request completed with the generic success notice, as expected for an absent
  account. Real email delivery and credential use still require a registered
  active account and an inbox round trip.
