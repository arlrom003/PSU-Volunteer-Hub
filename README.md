# PSU Volunteer Hub

PSU Volunteer Hub is a centralized volunteer-management platform for Pangasinan State University. It supports public opportunity discovery, volunteer registration, campus-scoped coordination, attendance, descriptive analytics, reports, policy acknowledgements, and administrative governance.

## Continuation Status: 31 October 2026

Start with [HANDOFF.md](HANDOFF.md#current-handoff-31-october-2026) for the goal,
current state, decisions and reasons, ruled-out options, next step, relevant
files, verification commands, and the exact skills/rules used.

Both GitHub `main` branches were verified at `03d1fc1`. The original local branch
is still at `e2e9e6e` with mixed uncommitted edits. The latest Director layout is
integrated into the running local workspace, verified in the user's browser,
and **not committed or pushed**. See [DIRECTOR_DASHBOARD_QA.md](DIRECTOR_DASHBOARD_QA.md).
Do not confuse a local worktree, a GitHub push, and a deployed Railway revision.

Current local Director behavior: Worst Performing Campus uses the lowest exact
annual goal-achievement ratio; recognition and the complete university calendar
share the briefing row. Filters/exports and coverage live in Cross-Campus
Comparison. The campus chart and attendance-outcomes table remain in Analytics;
Admin analytics retains its controls. Preview buttons are removed from both
dashboards. Coordinator keeps five-item square pagination, its 2% PSU gold hero,
full calendar, and permanently visible Manage Activities.

Latest layout evidence is 200 targeted Python cases, four chart tests, and 219
browser assertions, plus 22 integration cases in the original workspace. This
documentation update runs no new application tests and makes no deployment or
database change. Native zoom, screen-reader, physical-device, and hosted checks
remain separate. Older results below are dated snapshots.

## What it does

- Public landing page, featured activities, opportunity search with multi-campus include/exclude filters, PSU volunteer joining, help guide, and 2020–2025 historical activity directory.
- Volunteer profiles with controlled interests and skills, cosine-similarity recommendations, image upload, a first-use guide, registration calendar, filtered history, and cancellation requests.
- Coordinator event creation and editing, agreements and optional NDAs, cancellation deadlines, announcements, attendance, external participants, milestones, reports, campus analytics, cancellation review, and campus calendar. The Coordinator console uses a staged Create Activity form, an operational attendance workspace, and compact secondary actions for activity management.
- Director cross-campus dashboard, activity accomplishments, target-versus-verified attendance, monthly calendars, descriptive analytics, ten-row paginated Live Activity Reports, and CSV/PDF exports.
- Admin user/campus/category management, deactivation/reactivation safeguards, validated CSV import/export, audit log, backups, Terms of Use, Privacy Notice, and default participation-agreement publishing.

Historical records are aggregate institutional reporting units. They are never represented as individual user accounts, registrations, attendance records, or verified hours.

## Requirements

- Python 3.10+
- MySQL 8.x or MariaDB 10.4+ for the shared database
- XAMPP MySQL is supported for local Windows development

SQLite can be used only for a self-contained local development database.

## Run locally

### PowerShell with MySQL

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="mysql+pymysql://root:@localhost/psu_volunteer_hub"
$env:FLASK_APP="app:create_app"
flask run --port 5000
```

Open `http://127.0.0.1:5000`.

### Self-contained SQLite development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///psu_local.db"
$env:FLASK_APP="app:create_app"
flask run --port 5000
```

For production, set a non-default `SECRET_KEY` and a MySQL `DATABASE_URL`. Do not commit either value.

## Production Startup

For the existing Railway thesis demo and deployment boundaries, see
[RAILWAY_DEMO_DEPLOYMENT.md](RAILWAY_DEMO_DEPLOYMENT.md). Earlier local Docker
checks are recorded in [DOCKER_DEMO_QA.md](DOCKER_DEMO_QA.md). Main/demo recovery
flows were user-confirmed on 29 October; deployment of later GitHub revisions
has not been independently verified here. Do not upload private database exports
or existing user files, and do not initialize an existing database from this guide.

Use `wsgi:app`, which explicitly selects production configuration, rather than
`app:app` or the development server. For Linux/WSL hosting with the installed
Gunicorn dependency, after securely configuring environment variables:

```sh
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

Gunicorn does not run natively on Windows. Choose the actual hosting platform
before finalizing its service and reverse-proxy configuration. This command is
not a complete HTTPS deployment; keep the WSGI port private behind the proxy.

- Production requires `SECRET_KEY` and `DATABASE_URL`, enables secure session
  cookies, and uses `TRUSTED_PROXY_COUNT` for the real trusted proxy topology.
- Production startup performs no `create_all` or automatic catalogue/demo/account
  seeding. Prepare schema, reference data, and a uniquely secured first Admin
  through an approved provisioning procedure before serving requests. Existing
  accounts and data are not deleted or repaired by this startup change.
- `APP_ENV=production` also selects production for the default factory used by
  Flask CLI and `app.py`; explicit factory arguments take precedence. Unknown
  environment names fail instead of falling back to development.
- `python app.py` is development-only and refuses to run with production settings.
  Local development defaults and explicit `create_app('testing')` keep their
  existing initialization behavior. Demo commands remain explicit operator actions,
  not production startup steps.
- For any new deployment, verify provisioning, HTTPS, persistent uploads, email
  delivery and recovery backups, and address historical SQL exposure. The current
  Railway apps use Brevo HTTPS email delivery; their status is recorded in
  `PASSWORD_RECOVERY_QA.md` and `RAILWAY_DEMO_DEPLOYMENT.md`.

### Explicit fresh-database provisioning

After a database administrator creates a **new, empty** target database, configure
`DATABASE_URL` and `SECRET_KEY` securely for that target. Do not point this command
at your existing Volunteer Hub database. While the application is offline, run:

```sh
flask --app wsgi:app init-production --database YOUR_NEW_EMPTY_DATABASE
```

Replace the placeholder with the exact database name in `DATABASE_URL`. Review
the displayed host/database, then confirm interactively. Enter the first Admin's
name, email and a unique password of at least 12 characters; password entry and
confirmation are hidden. There is no password command-line option or default.
The command refuses non-production configuration, mismatched names and any
existing table/view. It creates the current model schema, campuses, categories,
interests, skills, SDGs and one Admin, never demo events or extra users.

Run only one provisioner with exclusive access to the empty target. MySQL/MariaDB
DDL is not transactional: if setup fails, data writes are rolled back but schema
may remain. The command refuses a rerun on that schema; inspect and recover the
disposable target manually, rather than dropping tables automatically. Existing
databases still require reviewed incremental migrations. Do not apply old ALTER
migrations to the fresh current-model schema without comparing it first.

This command passed isolated SQLite checks and actual MariaDB provisioning on a
new disposable database, including first-Admin login and second-run refusal.
See `PRODUCTION_INIT_QA.md`; this is not hosted-deployment approval.
The subsequent full regression run passed all 352 tests in one run; the user
approved publishing this verified feature, tests and documentation.
Policies, uploads, backups, HTTPS and email delivery require operator
configuration/verification for each target. Current Railway email verification
is recorded below; encrypted off-site recovery remains unfinished.

## Demo accounts

Fresh demo databases create these accounts with password `password`.

| Role | Email | Main capabilities |
| --- | --- | --- |
| Student Volunteer | `student@psu.edu` | Profile, recommendations, opportunities, registrations |
| Faculty Volunteer | `faculty@psu.edu` | Same volunteer capabilities |
| Staff Volunteer | `staff@psu.edu` | Same volunteer capabilities |
| Extension Coordinator | `coordinator@psu.edu` | Campus activities, attendance, participants, reports |
| Director | `director@psu.edu` | Cross-campus analytics, calendars, reports |
| Admin | `admin@psu.edu` | User, campus, category, policy, and audit governance |

## MySQL migrations

For an existing MySQL database, apply each migration that has not already been applied, in date order. In PowerShell:

```powershell
Get-Content -Raw ".\migrations\20260912_policy_lifecycle.sql" |
  & "C:\xampp\mysql\bin\mysql.exe" -u root psu_volunteer_hub

Get-Content -Raw ".\migrations\20260916_first_use_guide.sql" |
  & "C:\xampp\mysql\bin\mysql.exe" -u root psu_volunteer_hub

Get-Content -Raw ".\migrations\20261016_director_demographics_sdgs.sql" |
  & "C:\xampp\mysql\bin\mysql.exe" -u root psu_volunteer_hub

Get-Content -Raw ".\migrations\20261016_security_hardening.sql" |
  & "C:\xampp\mysql\bin\mysql.exe" -u root psu_volunteer_hub
```

The earlier migrations in `migrations/` are also required for a database created before their feature sets. Do not rerun a migration containing non-idempotent `ALTER TABLE ... ADD COLUMN` statements.

Verify the latest onboarding migration:

```powershell
& "C:\xampp\mysql\bin\mysql.exe" -u root -e "USE psu_volunteer_hub; SHOW COLUMNS FROM users LIKE 'first_use_guide_dismissed_at';"
```

## Historical and panel-demo data

Import audited 2020–2025 aggregate activity data:

```powershell
flask import-historical-activities data/historical_activities_2020_2025.csv
```

Validate the source without modifying the database:

```powershell
flask import-historical-activities data/historical_activities_2020_2025.csv --dry-run
```

Seed representative live events, registrations, and attendance for a local panel demonstration:

```powershell
flask seed-demo-analytics
```

The historical import and demo seed are idempotent. Historical imports remain separate from live activity data.

For the larger, account-preserving fixture replacement, see
[`DEMO_DATASET_QA.md`](DEMO_DATASET_QA.md). The separate Railway demo app must
receive that code before `reset-and-seed-demo --database railway` is available.
Use its `--dry-run` preview to verify the demo database target before replacement.

## Policies and cancellations

Policy source texts are included in `docs/TERMS_OF_USE_v1.0.txt` and
`docs/PRIVACY_NOTICE_v1.0.txt`. Committing those files does not publish an active
database revision or establish institutional/legal approval. An authorized
administrator must review and publish approved content through the existing
policy-management screens. Registration disclosures depend on active revisions.

Public activity joining requires PSU sign-in. The former public guest form is
retired; its legacy entry URL redirects to sign-in. Coordinators can still record
external participants for an activity, and existing signed management links remain.

Activity details are publicly readable at `GET /opportunities/<event_id>` without
exposing consent bodies or participant records. Listing titles, View details and
homepage featured-details links open this page. Volunteers review agreements in
the existing authenticated joining step; successful joining returns to details
with database-backed status and a My registrations link. Only existing listing
filter/page keys are carried through Back links and sign-in. See
`OPPORTUNITY_JOURNEY_QA.md` for isolated verification and browser-check limits.

- Admins publish versioned Terms of Use, Privacy Notice, and default Participation Agreement revisions.
- New users acknowledge active Terms and Privacy revisions. Existing users are prompted after a newly published revision.
- Every event registration stores the accepted participation-agreement version; events may have their own agreement and optional NDA.
- Volunteers request cancellation before the event deadline. A campus coordinator approves or rejects the request; approval changes the registration to cancelled.
- My registrations links to activity details and shows the effective cancellation
  deadline, request outcome and private review notes. PSU volunteers can submit
  one cancellation request per registration; rejection does not enable another
  request. A restored registration retains its previous decision. Recorded attendance
  and deadline/status restrictions are enforced consistently on the dashboard and
  server. See `REGISTRATION_CANCELLATION_UI_QA.md` for isolated verification.

## Reports and analytics

- Participation is measured through registrations and verified present attendance. Service-hour values are not used in current analytics or exports.
- Director Live Activity Reports display ten rows per page while CSV/PDF exports include every activity matching the active filters.
- Filters and campus boundaries apply to reports. Coordinators are restricted to their campus; Directors are read-only across campuses.

## Coordinator workspace and responsive tables

- Create Activity keeps operational details and volunteer requirements visible, while optional targets, agreements, NDAs, and cover images are grouped in a native Additional settings disclosure. Submitted optional values reopen that disclosure after a validation error.
- Attendance starts with today's and upcoming campus activities, shows its timing state and roster totals, and retains individual, bulk, and final-save controls within the existing authorization and timing rules.
- The Coordinator activity workspace keeps attendance as the primary action; editing, milestone uploads, and announcements are grouped in More actions, while activity removal stays separate with its existing confirmation.
- On small screens, operational record tables reflow into labelled records. Dense reports remain inside labelled horizontal scroll regions so the page itself does not scroll sideways.

## Inactivity timeout

All four roles time out after 30 minutes without acknowledged activity, with a
1-minute browser warning and a Stay signed in action. Expiry is checked on the
server before protected route actions; an expired session cannot be renewed.
Status reads and static files do not keep a session alive. Sign-in remains
session-only, without a persistent remember cookie. Unsaved work is not saved
automatically. See `SESSION_IDLE_QA.md` for verification and signed-cookie limits.
Final local regression on 21 October 2026: 393 passed in 986.10s using isolated
SQLite, plus focused browser checks. No live data or deployment changes.

## Tests

For the 22 October combined release, see `RELEASE_2026_10_22.md` for current
focused results (**106 passed in 260.39s**), included changes and outstanding
checks. The full 393-test run
on 21 October belongs to the inactivity implementation snapshot; the combined
release has not received a new complete regression run. Earlier verification
paragraphs below are historical records, not today's deployment-readiness status.

```powershell
python -m pytest tests -q
```

Historical full local verification on 18 October 2026 completed with `277 passed`,
zero failures, using isolated SQLite test databases. This includes the Admin
password-reset/session checks and the recent joining, redirect, homepage timing,
dashboard, and profile regressions.

The subsequent campus-filter enhancement passed 49 focused checks plus isolated
desktop/mobile browser checks with scripts blocked. See `CAMPUS_FILTER_QA.md`;
the full suite has not been rerun since that enhancement.

Subsequent analytics search/multi-campus work passed 68 reporting/analytics/UI
regression checks plus 3 final-code follow-ups. The actual MariaDB database passed
18 read-only report checks. A four-role browser review used a disposable copy of
actual data and found two unresolved issues: cancellation approval loses its
submit-button decision, and future attendance can produce premature completion
and certificate eligibility. See `ROLE_BROWSER_QA.md` for evidence and scope.

Local follow-up, 20 October 2026: the shared form-submit loading script now
preserves cancellation decisions and prevents duplicate submits. 18 focused
backend/UI checks and 6 Node.js behavioral checks passed; the Node checks also
run through pytest when Node.js is installed (otherwise explicitly skipped).
Browser Approve/Reject passed with CSRF in isolated SQLite. MariaDB-copy retest
remains pending because MariaDB was stopped. See `CANCELLATION_REPAIR_QA.md`.
Attendance follow-up, 20 October 2026: server-side timing checks now prevent
attendance writes before the scheduled end (start fallback for legacy no-end
activities), with an explanatory notice and disabled controls. Final focused
timing/cancellation/UI run: 22 passed; broader attendance/UI run: 56 passed,
plus one added external-participant timing case. Browser checks used isolated
CSRF-enabled SQLite. Existing records were not rewritten. Both repairs remain
local/uncommitted; full suite and copied-MariaDB rerun remain pending.
See `ATTENDANCE_TIMING_QA.md`.

Latest approved refinement: check-in opens 30 minutes before start. Early Present
saves remain Confirmed and certificate-ineligible; the coordinator saves final
attendance at/after the scheduled end (legacy start fallback) to confirm completion.
This replaces the end-only attendance lock described above. No automatic finalization.

Release verification follow-up: both repairs passed copied-MariaDB browser checks
on 20 October 2026, including the same registration's early check-in to final
attendance transition. See `REPAIR_RELEASE_QA.md` for the full automated run,
environment-related reruns, and source-isolation checks. Earlier pending notes
above are delivery-time snapshots. The user subsequently approved including these
verified repairs, tests, roadmap and QA documents in the 20 October publication.

Coordinator UI refinement, 22 October 2026: responsive table, activity-action,
attendance-workspace, and Create Activity form checks were run against isolated
tests and temporary local previews. The Create Activity regression set passed
five checks; the responsive-table regression set passed four checks. These are
focused local checks, not a new full-suite or deployment claim.

## Production security checklist

- Set strong, unique `SECRET_KEY` and `DATABASE_URL` environment variables; the app refuses to start in production without both.
- Deploy behind an HTTPS reverse proxy and set `TRUSTED_PROXY_COUNT` to the number of trusted proxies. Do not expose the Flask development server publicly.
- Use a dedicated MySQL application account with only the database privileges the app needs; never deploy with MySQL `root` credentials.
- Configure working email delivery before enabling public password resets; see the email setup below.
- Back up MySQL regularly, encrypt backups, and test restoration before each release. Apply migrations to a backup/staging copy first.
  See `BACKUP_RESTORE_RUNBOOK.md` and the scoped local results in
  `BACKUP_RESTORE_QA.md`. The local drill passed for database and existing public
  files, not encrypted off-site recovery or private-file restoration.
- Keep `PRIVATE_UPLOAD_FOLDER` outside the web root. New milestone uploads are private and are downloaded only through role-checked routes.

## Password recovery email setup

Status, 29 October 2026: Brevo HTTPS delivery is configured on the main and demo
Railway apps. The user confirmed receiving the email, signing in with the
temporary password, choosing a permanent password and signing in with it on
both apps. Agent checks verified provider access and database connectivity;
the agent did not inspect the user's inbox or enter their credentials. See
`PASSWORD_RECOVERY_QA.md` for test evidence and remaining limits. The setup
instructions below remain applicable to new environments.

Forgot password emails a random temporary password to the active account's
registered email. Enter it on the sign-in page to choose a new password before
accessing the account. It expires after 30 minutes, only the latest one works,
and completing the reset invalidates it and signs out existing sessions.
Requesting a reset leaves the current password unchanged. No schema migration
is needed: recovery uses the existing `password_reset_tokens` table.

### Brevo HTTPS API (recommended for Railway)

1. Create or sign in to your [Brevo account](https://app.brevo.com/).
2. Under **Settings > Senders, Domains, IPs**, add a sender named
   **PSU Volunteer Hub** with an email address you control. Complete sender
   verification and authenticate your sending domain using Brevo's DNS records.
   A PSU address requires authorization and DNS help from the university's IT team.
3. Under **Settings > SMTP & API > API Keys**, generate an API key for this app.
   Use an **API key**, not an SMTP key, for the HTTPS integration.
4. Set these variables in your untracked `.env` file (local use) or in your
   deployed app's private environment variables:

   ```dotenv
   MAIL_PROVIDER=brevo
   BREVO_API_KEY=your-private-brevo-api-key
   MAIL_DEFAULT_SENDER=your-verified-sender@example.com
   MAIL_SUPPRESS_SEND=false
   ```

5. Restart or redeploy the app, request a reset for a registered test account,
   and check **Transactional > Logs** in Brevo and the recipient's inbox/spam.
   A provider-accepted request does not by itself prove inbox delivery.

The app posts to `https://api.brevo.com/v3/smtp/email` with a 15-second timeout.
No extra SDK is needed. Missing keys, rejected requests and connection errors
follow the existing failure path, preserving the current account password and
previous recovery credential. Keys and email bodies are not logged.

Railway Free, Trial, and Hobby block outbound SMTP; use the HTTPS integration
on these plans. [Railway email delivery rules](https://docs.railway.com/networking/outbound-networking).
Brevo setup: [sender verification](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email),
[API authentication](https://developers.brevo.com/docs/authentication-schemes),
[sending email](https://developers.brevo.com/docs/send-a-transactional-email).

### SMTP alternative

Set `MAIL_PROVIDER=smtp` and these variables in your untracked `.env` file
or hosting provider's environment settings:

- `MAIL_SERVER`: your provider's SMTP host.
- `MAIL_PORT`: your provider's port, usually `587` for STARTTLS or `465` for SSL.
- `MAIL_USE_TLS=true`, `MAIL_USE_SSL=false` for STARTTLS; reverse them for SSL.
  Enable only one.
- `MAIL_USERNAME` and `MAIL_PASSWORD`: your sender account's SMTP credentials.
  Use a provider-issued app password when required.
- `MAIL_DEFAULT_SENDER`: a sender address authorized by your provider.
- `MAIL_SUPPRESS_SEND=false`: required for delivery, including local development.
  Development suppresses delivery by default; automated tests always suppress it.

Restart the app after changing configuration. Request a reset for a real
registered test account, check inbox and spam, sign in with the temporary
password, choose a new password, and verify the temporary password no longer
works. Automated tests use captured email and mocked SMTP; they do not prove
live inbox delivery. A server log reporting `Password reset email delivery failed`
means the email provider connection, sender, or credentials need checking. The public
response stays generic to protect account privacy. Never commit real credentials.

For Gmail or Google Workspace, use `smtp.gmail.com`, port `587`, and
`MAIL_USE_TLS=true`. Set both sender fields to your full Google email address.
Enable 2-Step Verification, then generate an App Password for PSU Volunteer Hub
and save it as `MAIL_PASSWORD`; do not use your regular Google password.
See [Google's App Password instructions](https://support.google.com/mail/answer/185833)
and [Google's SMTP setup](https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app).
If App Passwords are unavailable for your managed account, ask the Workspace
administrator which SMTP relay or permitted sender account to use.

## Technology

- **Backend:** Flask, SQLAlchemy, Flask-Login, Werkzeug
- **Database:** MySQL/MariaDB; SQLite for isolated development
- **Recommendations:** content-based cosine similarity using scikit-learn
- **Frontend:** Jinja templates, Bare CSS, Material Symbols, locally bundled Plotly
- **Media:** Pillow validation for uploads
- **Reports:** ReportLab PDF and CSV exports
- **Testing:** pytest

## Repository hygiene

Do not commit database exports, `.env` files, virtual environments, or uploaded user files. In particular, keep `Database/psu_volunteer_hub_after_policy_lifecycle.sql` local because it can contain real account data.

This revision removes the two previously tracked full SQL dumps from source
tracking; local copies are preserved and ignored by `Database/*.sql`.
Earlier commits will continue to contain them even after an ordinary removal
commit. History cleanup and any exposed-account response require separate review.

For development, use an isolated empty database and the existing synthetic demo
initialization, never a real account export. For existing production databases,
use reviewed scripts under `migrations/`, applying only missing migrations on a
backup/staging copy first. These incremental scripts are not a complete fresh
production bootstrap. A reviewed schema-only baseline and explicit first-Admin/
reference-data provisioning are still needed for a new deployment. See
`Database/README.md`; do not use the local full dumps as a production setup artifact.
