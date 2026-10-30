# PSU Volunteer Hub — Continuation Handoff

## Demonstration dataset command (30 October 2026)

`reset-and-seed-demo --database railway` provides a read-only
`--dry-run` preview and explicit typed target confirmation. It preserves all
existing login accounts/passwords, including the required student, coordinator
and director accounts, and replaces only marked demo records. The new fixture
contains 200 events, 5,000 registrations, 4,000 attendance, 200 external volunteers,
150 cancellation requests and SDG mappings across the existing campuses.
Focused isolated CLI/import/provisioning checks: 15 passed in 27.58 seconds.
See `DEMO_DATASET_QA.md` for exact scope, target checks, limitations and commands.
Publication of this command, tests and related documentation is authorized to
`thesis/main`. Hosted deployment and database execution remain unverified.
Unrelated security/recovery changes remain local and outside this publication.

## Start here in a new chat

The user can say: **Read HANDOFF.md and continue from the current local files.**

1. Read this file, `VOLUNTEER_HUB_ROADMAP.md`, `DASHBOARD_REDESIGN_QA.md`, and
   `PROFILE_REPAIR_QA.md`. Inspect `git status` and the actual local changes
   before editing; do not assume GitHub contains the latest iteration.
2. Preserve the dashboard redesign, first-use walkthroughs, volunteer profile
   repair, and any uncommitted changes. Do not discard or overwrite unrelated work.
3. Read the applicable installed skills completely before using them:
   - **`ponytail` (full):** use existing helpers, native controls, and the smallest
     safe, maintainable implementation. Do not sacrifice validation or accessibility.
   - **`antislop` + `antislop-ui`:** apply during implementation, not only after it.
     Retain purposeful PSU styling and complete the delivery gate.
   - **`frontend-design`:** use for interface changes to improve hierarchy,
     typography, spacing, composition, and clear primary actions.
   - **`antislop-human`:** verify contrast, semantic labels, keyboard operation,
     visible focus, and understandable empty/error/selected states.
   - **`antislop-layoutmobile`:** verify intentional mobile reflow, 44px targets,
     long-content wrapping, and contained table scrolling.
   - **`web-design-guidelines`:** review the completed UI against the skill's
     current guidelines, address in-scope findings, and report remaining limits.
   These are installed skill names; resolve their paths from the current session's
   skill catalog rather than assuming a location on another laptop. If unavailable,
   report that limitation; do not silently claim the skill was used or install one
   without authorization.
4. Reuse Bare CSS, the single `static/styles/base.css`, shared role shell/sidebar,
   role stylesheets, and local PSU assets. No Bootstrap/Tailwind migration,
   dependency, new foundation stylesheet, or unrelated redesign without approval.
   Keep the institutional direction: ENERGY 1 / RHYTHM 2 / MOTION 1.
5. Preserve Flask routes, CSRF, authorization, MySQL schema, and cosine
   recommendations unless the next request explicitly changes them. Verify real
   controls and desktop/mobile layouts; distinguish isolated test data from live data.
6. If the user supplied a next task, proceed with it. Otherwise briefly summarize
   the current status and ask which improvement to work on next. Do not commit,
   push, seed, or alter the live database just because this handoff was read.

## Repository and local run

23 October publication follow-up: the user approved committing and pushing the
baseline test reconciliation and its documentation. Local/unpublished and
no-commit/push statements below describe the verification-time snapshot, not a
continuing restriction. Verify actual publication with HEAD and GitHub main.
No production behavior, live database or deployment change is included.

23 October baseline-test reconciliation (local, unpublished): the three failures
were reproduced before editing (3 failed in 9.86s). Only tests and documentation
changed: Director assertions now separate live navigation/export context from
historical forms and verify actual filtered rows; profile assertions identify
Certificate cells within their activity rows, including all ineligible attendance
cases. Production files remain unchanged from be44a31. Focused verification:
97 passed in 233.32s, plus 3 dashboard scope/count checks in 0.35s. Final full
suite: 458 passed in 1141.90s, zero failures/errors/skips. All three baseline
assertions are reconciled without production changes; the automated suite is
green. See REGRESSION_RECONCILIATION_QA.md for evidence.
Earlier counts below remain historical snapshots. Actual browser zoom,
screen-reader and physical-mobile checks remain separate release gates.
No live database access, schema changes, deployment, commits or pushes.

Publication follow-up, 22 October 2026: the user approved committing and pushing
the opportunity journey and registration/cancellation refinement together, before
addressing the three baseline test assertions. This revision includes both QA
reports and their tests. Earlier local/unpublished statements below describe the
verification-time snapshots; confirm actual publication with HEAD and origin/main.
No live database, deployment, policy activation or schema change is included.

22 October registration/cancellation refinement (local, unpublished): activity
links and deadlines now appear in My registrations; cancellation decisions are
separate, private native disclosures. Shared PSU cancellation checks prevent the
attendance/action mismatch and repeat requests after any existing decision under
the user-selected one-request rule. Inline form errors retain values; whitelisted
dashboard context returns to the affected record. No new routes/schema/dependencies.
See REGISTRATION_CANCELLATION_UI_QA.md for final tests, screenshots and manual limits.
Final focused selection: 66 passed in 165.81s, including shared UI structure.
Final uninterrupted full suite: 450 passed, 3 known baseline failures in 1130.79s.
The initial sandboxed attempt could not finish its summary; the final run used
working test-process/temp-folder permissions and had no environment errors.
No new registration/cancellation failures; the full suite is not yet green.
The prior uncommitted opportunity journey is retained. No live DB or Git publication.

22 October opportunity journey (local, not committed or pushed): the approved
listing/details/consent remake is implemented. Public read-only details live at
`GET /opportunities/<int:event_id>`; authenticated joining retains its existing
endpoint and redirects to database-backed confirmation on details. Listing query
keys are whitelisted through Back links and sign-in. Homepage featured details
now use this page; hero/carousel behavior is retained. See OPPORTUNITY_JOURNEY_QA.md
for current verification, screenshots and remaining physical-device/zoom limits.
Final isolated full suite: 413 passed, 3 failed in 1033.25s; all three failures
reproduce on untouched committed baseline 21a0545 (two Director-filter assertions
and profile responsive-cell markup). Focused journey/filter run: 43 passed;
shared UI structure: 6 passed. Do not describe the full suite as green.
No live database writes, migration, dependencies, deployment or publication.
Earlier release approval below does not authorize publishing this new work.

22 October release scope: the user approved committing all current application
changes and requested documentation updates before pushing to GitHub main.
See RELEASE_2026_10_22.md for scope, current verification and remaining gates.
The Coordinator workspace baseline is already in commit 8c22e5f. Earlier
local/uncommitted statements below are dated implementation snapshots, not a
claim that every listed change remains unpublished. Confirm actual publication
with git status/log and the remote rather than treating approval as push success.

Publication note, 18 October 2026: this follow-up revision includes the joining,
authentication/session, homepage timing, campus-filter, and activity-search
improvements plus their QA reports and the preserved roadmap refresh. Earlier
"local and uncommitted" statements below describe their delivery-time snapshots.
Publication revision, 20 October 2026: includes the verified cancellation and
early-check-in/final-attendance repairs, tests, and QA documents. The user approved
commit and push after release verification. Earlier local/uncommitted/pending
statements are delivery-time snapshots; see REPAIR_RELEASE_QA.md for final results.
Copied databases, uploads,
diagnostic scripts, screenshots, and downloaded reports are not included in Git.

- Repository: `https://github.com/Xed-stack/Psu_VolunteerHub`
- Branch: `main`
- Current local workspace: `C:\Users\arlro\Desktop\PSU VOLUNTEER\Psu_VolunteerHub`
- Start MySQL from XAMPP, then run the Flask application with:

  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```

- The expected local URL is `http://127.0.0.1:5000`.

## Completed local work

### Consolidated release preparation (22 October 2026)

- Includes the login/signup remake, session-only login and inactivity timeout;
  retirement of public guest signup; signed-in Help navigation; Director
  live/historical view context; policy source documents; and local Docker and
  backup/restore preparation with QA reports.
- Public event joining now requires PSU sign-in. Authorized coordinator entry
  of external participants and existing signed external management links remain.
- Current focused publication checks: **106 passed in 260.39s**, zero failures;
  see RELEASE_2026_10_22.md for the command and coverage.
  The 393-test full run below belongs to the 21 October timeout snapshot, not
  an assertion that all later changes received a new full-suite/browser review.
- No live policy publication, migration, seed, cloud deployment or paid hosting
  change is part of this release operation. Local attachments, credentials,
  database exports, runtime uploads and private QA artifacts stay out of Git.
- Next unfinished gate: full regression on this combined revision, then remaining
  real-browser accessibility checks. Railway remains deferred pending approval.

### Coordinator workspace refinement (22 October 2026, local)

- Coordinator management now prioritizes attendance, groups edit, milestone-upload,
  and announcement work in a native More actions disclosure, and keeps permanent
  activity removal visibly separate with its existing confirmation.
- Attendance presents today's activities and the next scheduled activities first,
  then the full campus picker, plain-language timing guidance, roster totals, and
  native-confirmed bulk present/absent controls. Save remains the only persistence
  action; server timing, campus scope, CSRF, and attendance validation are unchanged.
- Create Activity is staged into Activity details, Volunteer requirements, and a
  native Additional settings disclosure. Optional values reopen the disclosure
  after validation errors. The mobile action bar keeps Cancel and Publish Activity
  reachable with safe-area spacing.
- Authenticated operational tables reflow to labelled records on mobile. Dense
  reports keep readable columns in a labelled internal scroll region; desktop
  tables remain unchanged.
- Verification: `tests/test_responsive_tables.py` passed 4 focused checks and
  `tests/test_create_activity_form.py` plus three existing create/scope checks
  passed 5 focused checks. Compilation and whitespace checks passed. Temporary
  local previews checked the form at desktop, 390px mobile, and a 200%-equivalent
  narrow viewport; no live database data was created or changed.

### Inactivity timeout (21 October 2026, local)

- User chose 30-minute inactivity expiry with a 1-minute warning for all roles.
  Shared server guard, non-renewing GET /auth/session, CSRF-protected renewal,
  native warning in all three layouts and explicit inactivity sign-in message.
- Keeps signed-cookie/session-only authentication, auth_version invalidation,
  policy gates and existing role authorization. No DB migration or live writes.
  Legacy sessions get first-request grace; no central revocation store added.
- See SESSION_IDLE_QA.md and tests/test_session_idle.py. Final 20 focused checks
  and 7 Node checks passed. Browser role/workflow/mobile/keyboard/multi-tab checks
  completed on isolated SQLite; preview stopped. Final uninterrupted full suite:
  **393 passed in 986.10s**, zero failures. Syntax and diff checks passed.
  Preserve the uncommitted login/signup remake and docs/policy files.
- Railway, live policy publication, commits and pushes remain outside this task.

### Railway thesis-demo preparation (latest local work)

21 October follow-up: Docker image successfully built and tested locally.
Network-isolated Gunicorn startup, upload symlink and public/private probe plus
synthetic SQLite data persistence across two containers passed. 18 focused tests
passed in built Linux environment. Both smoke containers stopped; synthetic
volume retained. See DOCKER_DEMO_QA.md. Supersedes engine-stopped/build-pending
notes below. No cloud writes, original DB access, commit/push or paid upgrade.
Next: inspect actual Railway trial allowance before creating demo services.

- User has Railway account; aim is separate synthetic thesis demonstration, no
  paid upgrade authorized. Dockerfile/.dockerignore prepared with explicit code
  allowlist, Python 3.11, existing dependencies, Gunicorn wsgi:app and PORT.
- App volume design: /data/public via static/uploads symlink, /data/private for
  milestones. Requires actual mounted /data volume plus separate MySQL volume;
  trial vs ongoing Free limits must be checked before cloud creation.
- See RAILWAY_DEMO_DEPLOYMENT.md. 20 focused deployment/startup/provisioning checks
  passed. Docker CLI installed but Linux engine stopped; no image build or cloud
  deployment verified. No legacy railway.json (deprecated per current docs).
- Pending backup documents preserved. No source DB changes, cloud writes, image
  upload, commit/push or paid upgrade. Next: start Docker Desktop to build/test
  the image, inspect Railway trial allowance, then approve scoped demo deployment.

### Backup/restore drill (latest local work)

- Added BACKUP_RESTORE_RUNBOOK.md and BACKUP_RESTORE_QA.md. Native MariaDB dump
  restored into new psu_volunteer_restoreqa_20261020_0bbf28ad: all 31 schemas and
  1,167 row fingerprints matched; 2 public uploads matched after file restore.
  Original DB and upload fingerprints unchanged. Private upload root had 0 files.
- Restored ORM queries and production login-page HTTP test-client smoke passed.
  No actual user authentication, browser or hosted TLS claim. No app-code change.
- Restricted plaintext artifacts outside Git retained under visualization folder
  backup-restore-drill-0bbf28ad; credentials temporary/removed. No commit/push or
  deletion. Not encrypted off-site recovery; private files, independent-host
  restore, scheduling/retention/alerts, encryption/key recovery remain gates.

### Explicit production initialization (latest local work)

Publication follow-up: user approved commit/push after the 352-test full run and
actual disposable MariaDB verification. Local/pending-publication notes below
are prior snapshots. No deployment or original database changes authorized.

Final regression follow-up: **352 passed in 885.51s**, one uninterrupted full
run with approved execution permission and fresh private QA temp directory.
No code/assertion edits required; scoped diff reviewed and diff check passed.
Ready for user commit/push approval. No publication or database changes in this
regression turn. See PRODUCTION_INIT_QA.md; earlier full-suite-pending notes below
are superseded. Hosting/recovery and historical exposure gates remain open.

MariaDB follow-up: verified on new disposable
`psu_volunteer_initqa_20261020_bfdd5f4c`: 31 tables, one working Admin, reference
catalogues only, no events/participation. Wrong target/decline/repeat refused.
HTTPS-scheme CSRF test-client login and Admin dashboard passed (not hosted TLS).
All original 31 table fingerprints unchanged, 1,167 rows. Test database retained;
no credentials saved. See PRODUCTION_INIT_QA.md. This supersedes the earlier
MariaDB-pending note below; full suite and deployment still pending.

- Added `flask --app wsgi:app init-production --database EXACT_EMPTY_NAME`.
  Production-only, exact configured database match, empty table/view guard,
  interactive confirmation and private password/confirmation (minimum 12 chars).
- Creates current model schema, existing institutional reference catalogues and
  exactly one Admin, no demo users/events. Existing reference helpers optionally
  defer commit so provisioning data commits together. Normal dev/test behavior
  retained. Production startup itself still performs no automatic writes.
- Failure rolls back data but may leave MySQL/MariaDB DDL; no automatic drop,
  retry or existing-schema resume. Requires one offline operator on a new target.
- Tested only isolated SQLite, including first-Admin login and fail-closed cases.
  Final provisioning/startup/app-init/historical-import selection: **24 passed**.
  Full suite not rerun. `git diff --check` passed (line-ending notices only).
  No actual database initialized, migration applied, commit/push or deploy.
  See tests/test_production_init.py and README. Actual MariaDB fresh-target
  verification remains required before deployment; historical dump issue deferred.

Publication revision, 20 October 2026: the user approved commit/push of production
startup safety, its regression tests, documentation and the SQL tracking removals.
Local/staged/uncommitted statements below describe the implementation snapshots.
The SQL files remain locally ignored; no history rewrite or database changes.
Fresh production provisioning, historical dump exposure and hosting/recovery
verification remain unfinished. Startup/app-init checks rerun: 12 passed.

### SQL dump tracking cleanup (latest local work, 20 October 2026)

- Removed Database/psu_volunteer_hub.sql and Database/psu_volunteer_hub_latest.sql
  from the Git index only. Both local files preserved; existing Database/*.sql
  ignore rule retained. Removal is staged, not committed/pushed.
- Verified both files still exist with identical before/after SHA-256 hashes,
  neither remains in git ls-files, and git check-ignore covers both.
- No history rewrite, live database changes, or account/password changes. Prior
  commits and current GitHub main still expose the dumps until separately handled.
- README and Database/README.md explain synthetic development setup, incremental
  migrations, and the remaining fresh-production schema/provisioning requirement.
  Preserve the pending production-startup work alongside this staged removal.

### Production startup safety (latest local work, 20 October 2026)

- `wsgi.py` explicitly selects production; default factory respects `APP_ENV`
  (development when unset) and rejects unknown names. Direct `app.py` refuses
  production development-server use and no longer forces debug on.
- Production factory skips `create_all` and all automatic seeds, including demo
  privileged accounts. Existing accounts are not changed. Development/testing
  initialization retained. No database migration or actual provisioning performed.
- Initial schema/reference-data/Admin provisioning is now a mandatory explicit
  deployment step, not a silently seeded production account. See README startup
  section and tests/test_production_startup.py. No deploy/commit/push authorized.
- Verification: production-startup tests plus existing app-init tests: **12 passed**
  in isolated SQLite. Production tests trap all initialization/seed calls and
  confirm no tables created. Development still creates 6 demo users / 9 events.
  Full suite and actual Linux/WSL Gunicorn/HTTPS deployment not rerun for this change.
- Remaining audit gates: tracked SQL dumps/history exposure, actual host/HTTPS/
  proxy/SMTP/uploads configuration, and full backup/restore verification.

### Release verification follow-up (20 October 2026)

Both local repairs now passed browser retesting on the existing disposable
MariaDB copy, with CSRF enabled and current repository static files. Early
check-in stayed Confirmed/Present; final attendance changed that same record to
Completed/Present without duplication. Desktop cancellation approval and mobile
keyboard rejection persisted correct decisions, notes, reviewers, audit entries
and notifications. Original database access was read-only; before/after counts
matched (31 tables / 1,167 rows), with no QA fixtures in the original.
See REPAIR_RELEASE_QA.md for automated results and isolation limits.
Automated: 334 collected; full run 328 passed plus six environment-blocked
outcomes, then Node/profile rerun 20 passed (14 overlapping), resolving all six.
All 334 have passing outcomes across runs, not one uninterrupted green run.
This supersedes earlier copied-MariaDB-pending notes below. No commit or push.

### Attendance timing repair (20 October 2026)

Latest approved refinement: check-in now opens exactly 30 minutes before start.
Before effective end, Present records attendance but leaves registration Confirmed
and certificate-ineligible. Coordinator must save final attendance at/after end;
legacy no-end activities retain the start fallback. This supersedes the original
end-only locking policy below. See the early-check-in follow-up in
ATTENDANCE_TIMING_QA.md. No automatic background finalization or migration.

- Attendance writes now require the scheduled end to have arrived, falling back
  to the start for legacy activities without an end. Exact-boundary saves are
  allowed. The server rechecks every POST before any attendance mutation.
- Upcoming/ongoing activities show the opening time and disabled native controls.
  Existing records are preserved; no retrospective data correction was performed.
- Verification: 56 broader attendance/external-participant/UI checks passed,
  one added external timing case passed, then the final timing/cancellation/UI
  run passed 22 checks. Browser confirmed future/ongoing locks and ended/legacy
  saves in isolated CSRF-enabled SQLite, plus contained 390px mobile layout.
- No migration, new dependency, commit, push, or source database writes.
  MariaDB was stopped; copied-MariaDB rerun and full suite remain pending.
  See ATTENDANCE_TIMING_QA.md. Next: verify both repairs on the disposable
  MariaDB copy and run the full regression suite before publication.

### Cancellation decision submission repair (20 October 2026)

- Fixed the shared form loading-state script, not the cancellation route.
  The clicked submit button retains its native name/value; `aria-disabled`
  marks the loading button while a form-level busy guard blocks repeat submits,
  including the other decision and implicit Enter. Existing spinner/busy feedback
  and pageshow restoration remain. Already-cancelled submits and opt-outs are left alone.
- Approval/rejection retain CSRF, campus/role checks, review notes, reviewer/time,
  registration state, audit entries, notifications, and final-decision safeguards.
- Verification: **18 backend/coordinator/UI checks passed**, plus **6 JavaScript
  behavior checks**, also passing through their pytest wrapper (**1 passed**).
  The JavaScript checks reproduced the bug before the fix. No new runtime dependency.
- Actual browser: desktop Approve and 390px keyboard Reject succeeded; both notes
  persisted and pending queue became empty. No console errors or mobile overflow.
- MariaDB was stopped (connection refused), including outside the sandbox.
  Browser verification therefore used an isolated CSRF-enabled in-memory SQLite
  preview, not the existing MariaDB copy. MariaDB-copy retest and full suite remain
  pending; no source database was started or changed. Preview was stopped/closed.
- Local/uncommitted, no push or migration. See CANCELLATION_REPAIR_QA.md.
  The future-attendance/certificate-eligibility issue is not part of this fix.

### Four-role browser QA on an actual-data copy (18 October 2026)

- User approved a disposable local MariaDB copy and dedicated role test accounts.
  `psu_volunteer_browserqa_20261018_a14c` matched all 31 source tables / 1,156 rows
  before fixtures. Server used localhost, CSRF, suppressed email, and copied uploads.
- Volunteer, Coordinator, Director, and Admin core browser workflows were exercised.
  **Two confirmed issues remain unfixed:** cancellation approval loses its named
  submit-button decision through the shared submit-state script; future activity
  attendance can immediately produce Completed/certificate-eligible participation.
- See ROLE_BROWSER_QA.md for reproduction steps, code evidence, role-by-role
  coverage, sampled authorization checks, evidence, and untested workflows.
- Original database connections were read-only. Post-review original counts and
  all 18 read-only report checks still passed; no QA accounts/activities existed
  there. No source migration, seed, password reset, or application-code fix.
- Test server stopped and browser closed. The disposable database and copied
  files remain locally for reproduction; do not publish copied personal data.
  No commit or push. Fixes require the user's next approval.

### Director live multi-campus filtering (18 October 2026)

- Director/Admin live analytics uses alphabetized native campus checkboxes with
  include/exclude modes. No choices means all campuses; exclusion retains
  unassigned activities. New live choices use repeated `campus` parameters.
- Live totals, comparisons, trends, SDG mapping, report pagination, downloads,
  and sex-disaggregated attendance use the selected live activity scope.
  CSV/PDF metadata names the selection and mode. Historical/award forms retain
  every repeated live choice when submitted.
- Historical reports and all-time home-campus affiliation evidence keep their
  separate single `campus_id` selection. Existing URLs using only `campus_id`
  still scope the live report; new `campus_mode`/`campus` parameters take
  precedence. Clear restores the unrestricted page.
- Invalid new campus choices/modes return an inline recoverable HTTP 400 with
  no live rows. Invalid CSV/PDF requests return HTTP 400, never a broader report.
- Coordinator routes remain account-campus scoped and ignore the new inputs.
  No new campus records, migration, dependency, foundation stylesheet, or JS.
- Isolated SQLite browser checks covered native keyboard inclusion/exclusion,
  invalid-choice recovery, desktop and 390px mobile. All campus targets were
  44px high; page widths matched the viewport. See ANALYTICS_CAMPUS_QA.md.
- Everything remains local and uncommitted; no live database change or push.
  Reporting/analytics/UI regression rerun: **68 passed**; final-code follow-up:
  **3 passed**, including an additional all-excluded/legacy-link case.

### Live activity-name search (18 October 2026)

- Director/Admin and Coordinator analytics now have a native GET search field.
  It matches a literal, case-insensitive title substring; surrounding whitespace
  is ignored. Blank search retains the existing report scope.
- The shared report builder applies search before totals, chart summaries,
  ten-row Director pagination, and CSV/PDF exports. Downloads record the search
  in metadata. Date ties use record ID for stable paging.
- Coordinator scope still comes from the authenticated account, never the URL.
  Director sex-disaggregated attendance also honors the title search. Historical
  source reports, annual recognition, and independently scoped profile/readiness
  evidence retain their existing scopes. No new View all interaction was added.
- Browser verification used isolated in-memory SQLite with CSRF enabled:
  desktop and 390px mobile, Enter submission, empty result, and Clear recovery.
  Mobile input height was 44px; page client/scroll widths both 375px.
- See ACTIVITY_SEARCH_QA.md for automated evidence and verification limits.
  Reporting/analytics/UI regression run: **57 passed**; final-code follow-up
  after attendance-table alignment: **3 passed** (including one additional case).
  All previous work is preserved. No migration, dependency, live database write,
  commit, or push.

### Opportunities campus filtering (18 October 2026)

- Public and signed-in Opportunities support alphabetized native campus
  checkboxes with include/exclude modes. No selection means all campuses.
- Repeated `campus` query parameters preserve selected campuses with search,
  category, mode, and pagination. Existing single-campus URLs remain supported.
  Exclusion keeps unassigned activities visible. Invalid/stale choices show a
  recoverable error and do not silently broaden results.
- Native disclosure, 44px controls, blue keyboard focus, mobile reflow, and a
  guest skip link reuse the existing role shell and base.css. No filter JavaScript,
  dependency, migration, or new stylesheet was added.
- Final focused verification: **49 passed**. Guest/volunteer desktop, tablet,
  mobile, long-name, and script-blocked browser checks passed. See
  `CAMPUS_FILTER_QA.md` for evidence and limits. The last full suite (277 passed)
  predates this enhancement; it was not rerun for this scoped change.
- All work remains local and uncommitted. No live database change or push.

### Admin password-reset repair (18 October 2026)

- Self-reset commits the password and audit entry, clears the active session,
  expires the remember cookie, and redirects to sign-in with an explicit success
  message explaining that the new password is required.
- Resetting another account preserves the acting admin's session and increments
  only the target's authentication version. Old target sessions expire on their
  next request, including remembered sessions in other browsers.
- Session clearing now precedes Flask-Login logout so its remember-cookie
  deletion flag survives. Existing authentication-version enforcement remains.
- The former failing assertion is replaced by separate self/other reset tests.
  **Six focused cases passed**, covering volunteer/admin targets, old/new
  passwords, remembered sessions, audit actors, short passwords, and CSRF.
- Final full suite: **277 passed, zero failures** in 728.56 seconds. This includes
  all recent joining, redirect, homepage timing, dashboard, analytics, and profile
  regression checks. Run with `python -m pytest tests -q -p no:cacheprovider` and
  a dedicated temporary test directory; Windows sandbox temp-folder permissions
  required running outside the sandbox. Test databases remained isolated SQLite.
- `git diff --check` passed. No migration, runtime dependency, live database
  change, commit, or push. Previous QA documents retain their historical results;
  the former Admin reset failure is resolved by this follow-up.

### Homepage completed-activity timing (18 October 2026)

- Completed story cards use the scheduled end time when recorded, falling back
  to the start time for legacy activities without an end. This is schedule-based
  classification and does not change verified participation or recognition.
- An activity qualifies at its effective end time. The three cards are ordered
  by latest effective end, with a stable record-ID tie-break. Featured activities
  must start strictly in the future, avoiding overlap at the exact start boundary.
- The ongoing-activity regression failed before the fix. Final verification:
  **32 public-experience, homepage joining, and UI-structure checks passed** in
  isolated SQLite, including eight new schedule/order cases. Existing layouts,
  assets, empty states, and historical/live data separation are unchanged.
- No migration, dependency, live database change, commit, or push. Full suite and
  browser visual checks were not rerun for this query-only change.

### Authentication return destinations (18 October 2026)

- Login and every Terms/Privacy continuation validate return destinations through
  one `_safe_next_url` helper. Only root-relative paths are accepted; external
  URLs, protocol-relative URLs, backslashes, and control characters (including
  encoded variants) fall back to the authenticated account's role dashboard.
- The login form retains `next` when submitting. A required Privacy Notice
  preserves the requested activity path/query after Terms acceptance.
- Verification: **41 authentication/return-flow tests and 16 compatibility tests
  passed** in isolated SQLite. The final URL guard also passed a separate attack
  vector rerun. Coverage includes all four role fallbacks, real rendered form
  submission, CSRF, policy acceptance branches, and return to agreement review.
- `git diff --check` passed. No visible UI redesign, migration, dependency, live
  database change, commit, or push. Full suite was not rerun; the existing Admin
  self-password-reset assertion remains outside this change.

### Joining flow repair (18 October 2026)

- Homepage featured-card and activity-dialog `Join Now` links open the existing
  agreement/NDA review screen before registration is submitted.
- The PSU registration route rejects both GET and POST requests at or after the
  activity start, including a submission from a previously opened review screen.
  A rejected request cannot restore a cancelled registration or replace its
  recorded agreement/NDA acceptance.
- Changed homepage action controls use PSU blue keyboard focus outlines.
- Verification: **19 volunteer-flow tests and 55 compatibility checks passed**
  using isolated SQLite. Desktop/mobile browser review and a successful preview
  registration were checked with CSRF enabled. See `JOINING_FLOW_QA.md`.
- No migration or live database change. Changes remain local and uncommitted;
  the pre-existing roadmap refresh is preserved.

### Volunteer profile repair (18 October 2026)

- `/profile` now uses the shared PSU header, bounded 96px photo, actual account
  details, separate interests/skills checkbox grids, accessible info tips,
  navigable recommendations, and five-row recent registration history.
- Name/email and other personal account details remain read-only. The unsupported
  `Verified volunteer` badge and duplicate read-only skills panel were removed.
- Registrations, verified present attendance, and completed participation are
  distinct counts. Completed participation requires completed registration status
  and present attendance, matching certificate eligibility. Count-based profile
  milestones use that count and are explicitly separate from Director recognition.
- Invalid submissions preserve submitted checkbox selections and show inline
  errors without changing stored preferences. Missing catalogs disable saving.
- JPEG/PNG/WebP uploads remain limited to 3 MB. A successful database commit
  precedes old-photo deletion; failed saves roll back and clean newly created
  files. Cleanup cannot remove shared assets or files outside the profile folder.
- Profile-specific CSS lives in `static/styles/volunteer.css`; no migration,
  dependency, framework, or profile JavaScript was added. Cosine matching remains.
- Latest verification: **19 focused profile tests passed**. Full suite:
  **227 passed, 1 known failure** in `TestAdminUserManagement.test_admin_reset_password`.
  That assertion expects a self-reset success message after redirects, but resetting
  the password invalidates the active session and reaches sign-in. It was not
  changed as part of the profile repair.
- Browser checks used isolated SQLite previews, not live MySQL. Desktop, tablet,
  390px mobile, keyboard controls, long names, and contained history scrolling
  were checked. Temporary preview servers were stopped afterward. See
  `PROFILE_REPAIR_QA.md` for evidence and explicit verification limitations.

### Director / Coordinator reporting redesign (18 October 2026)

- The two management dashboards and analytics screens share the PSU role shell, reusable heading/KPI/chart macros, and native information disclosures. Shared styles live in `static/styles/role-shell.css`; `base.css` remains the only global foundation.
- Live analytics has one filtered KPI strip. Campus/category comparisons, engagement trends, SDG mapping, composition, report pagination, and exports derive from the same `build_events_report` rows through `app/dashboard.py`. Historical aggregates retain a separate labelled source section and their own exports.
- Supplemental evidence states its scope: recognition is university-wide for the selected calendar year; profile demographics/affiliation and campus readiness/snapshot panels retain their independently labelled scopes.
- `/analytics` retains the ten-row live report and preserves every selected query parameter in pagination and CSV/PDF links. Coordinator reports remain restricted to the signed-in coordinator's campus.
- All four roles now use `static/scripts/first-use-tour.js`: native modal dialog, spotlight, keyboard controls, mobile coach sheet, and visible target selection. The former static Volunteer guide is removed. Help offers a plain `Show dashboard guide` replay link.
- `POST /guide/dismiss` is authenticated and CSRF protected and updates only `current_user.first_use_guide_dismissed_at`. The old volunteer dismissal URL remains compatible. Skip, Finish, and Escape share persistence; `?tour=1` replays without changing the stored timestamp.
- No new migration is required. Existing databases must already have `migrations/20260916_first_use_guide.sql` applied. This work adds no framework, runtime dependency, or database seed.
- Browser verification uses an isolated in-memory SQLite preview on port 5055, with CSRF enabled. This preview does not modify the deployment's MySQL data.
- Verification: 212 tests passed with the existing Admin self-password-reset message assertion still failing; final focused report/workspace/UI checks passed (10 tests). See `DASHBOARD_REDESIGN_QA.md` for browser evidence, the design gate, and native zoom/reduced-motion verification limits.

- Volunteer dashboard lists personal registrations, lets volunteers cancel eligible future registrations, and supports re-registration after a cancellation when capacity remains.
- Coordinators can permanently remove activities in their campus. PSU volunteers with registrations receive in-app cancellation notifications.
- Responsive sidebar behavior is mobile-only at 767px and below; mobile logout is a visible red outlined action.
- Historical participation remains visible in explicitly labelled source panels. The Director home campus comparison uses historical aggregates when live registrations are absent; filtered analytics comparisons use live report rows and do not silently substitute a different scope.
- Admin category management supports create/delete; deleted categories move affected events to `General` and notify the event creator or campus coordinators.
- Admin analytics is hidden from the admin interface while the route/template implementation remains available.
- The public `/opportunities` page now uses shared shell styling, responsive opportunity cards, CSRF-protected registration forms, and a clear `Registered` state for existing volunteer sign-ups.
- Analytics no longer displays or exports service-hour values; registration and attendance counts are the participation measures used throughout the UI and reports.
- The `seed-demo-analytics` Flask command creates idempotent presentation data across campuses, categories, registrations, and attendance without overwriting existing records.
- Phase 4 now includes an append-only Admin Activity Log, validated CSV user import/export (without password hashes), and versioned Terms of Use. An admin publishes the active terms revision; new registrations accept it during sign-up, while existing users are redirected to accept it before continuing.
- Accounts can be deactivated, request reactivation through the login flow, be reviewed in a Deactivated Users tab, and be permanently deleted manually after 30 days. Safeguards protect the last active admin and the current admin account.
- The roadmap in `VOLUNTEER_HUB_ROADMAP.md` records proposed future work. It is not implemented.
- Director demographics, SDG, and recognition are now implemented locally: volunteer sex is required at registration (existing volunteers complete it once after sign-in), coordinators tag activities with the official 17 SDGs, and Director Analytics shows sex-disaggregated verified participation plus calendar-year Top 5 recognition.
- Recognition is informational only: volunteers rank by verified present attendance then completed activities; campuses rank by verified attendance rate then verified present attendance. External, cancelled, absent, unverified, and historical aggregate records are excluded.

## Database requirement

Apply `migrations/20260903_admin_categories_and_deactivation.sql` to the configured MySQL database before testing the administration features on a fresh database. It adds activity categories, event creator ownership, and deactivation/reactivation fields.

Also apply `migrations/20260912_add_audit_logs.sql` and `migrations/20260912_add_terms_revisions.sql` for the Phase 4 audit and policy features on an existing database.

Apply `migrations/20261016_director_demographics_sdgs.sql` before using the Director demographics and SDG features against an existing MySQL database. Then restart Flask so the built-in SDG catalogue seed can verify the 17 official goals.

Apply `migrations/20261016_security_hardening.sql` before deploying the security update to an existing MySQL database. It adds session-version invalidation, database-backed authentication throttling, and password-reset tokens. Production also requires `SECRET_KEY`, `DATABASE_URL`, HTTPS behind a trusted proxy, a writable `PRIVATE_UPLOAD_FOLDER` outside the web root, and SMTP configuration for reset emails.

Historical CSV data can be imported with:

```powershell
flask import-historical-activities data/historical_activities_2020_2025.csv
```

For a local panel/demo dashboard with live registration and attendance charts:

```powershell
.\.venv\Scripts\flask.exe seed-demo-analytics
```

The command is safe to rerun. It creates records titled `[Demo Analytics] ...` only when they do not already exist. Run it only on a deliberately isolated development/demo database. Git transfers source, migrations and synthetic fixture code, not private SQL exports or a running database. If authorized data transfer is required, use an access-controlled encrypted backup outside Git and verify restoration separately; do not publish local full dumps.

## Recommended first checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
git status -sb
```

Then manually check:

1. A volunteer can register, cancel before the event start, and see the registration history.
2. A campus coordinator can only delete activities from their own campus.
3. A coordinator can create an activity using the staged form, expand Additional settings, and retain optional values after an invalid submission.
4. A coordinator can open More actions, use the activity controls, and see removal separated from routine actions.
5. A coordinator can open attendance on mobile, review the roster, and reach the final Save action without page-level horizontal scrolling.
6. A deactivated user sees the reactivation-request modal after valid credentials.
7. An admin can review Deactivated Users and categories without an Analytics navigation item.
8. The sidebar hamburger and red logout action render correctly at a mobile width and remain hidden/compact on desktop.

## Next recommended work

### Director demographics, SDG, and recognition phase

Implemented locally; apply the migration noted above before using it with an existing MySQL database. The policy lifecycle, cancellation review, Coordinator/Director calendars, accomplishment reporting, and first-use guide are already implemented. Apply `migrations/20260912_policy_lifecycle.sql` and `migrations/20260916_first_use_guide.sql` to an existing MySQL database before using those features there.

1. **Sex-disaggregated data**
   - Registration supports `Male`, `Female`, and `Prefer Not to Say`; legacy missing values remain `Not recorded`.
   - Redirect existing volunteers with no recorded value to complete it before accessing their dashboard.
   - Add a Director-only sex filter plus clearly labeled sex-disaggregated participation chart/table. Legacy records remain `Not recorded` until completed.

2. **Sustainable Development Goals (SDGs)**
   - [x] Seed the official 17 UN SDGs as a catalog.
   - [x] Let coordinators assign all applicable SDGs to an activity through a many-to-many relationship.
   - [x] Show assigned SDGs in the live report and PDF/CSV exports, with a Director SDG filter.
   - [ ] Show assigned SDGs in activity details/calendars and add a dedicated participation-by-SDG comparison when that reporting view is needed.
   - Keep historical aggregate records separate; never infer SDGs for them.

3. **Automatic annual recognition**
   - Add a Director-only calendar-year selector and Top 5 recognition lists.
   - Rank Outstanding Volunteers by verified present attendance, then completed activities; equal values share a rank.
   - Rank Outstanding Campuses by verified attendance rate, then total verified present attendance.
   - Exclude registrations without verified attendance, absences, cancellations, external participants, and historical aggregate data. The labels are informational; PSU retains final award approval.

4. **Verification**
   - Add a versioned MySQL migration for sex, SDG catalog, and the event–SDG relationship.
   - Test registration/profile completion, Director-only authorization, multi-SDG event editing/filtering, reporting, ranking order/ties/year scope, and zero-data states.
   - Run the full pytest suite and check Director analytics at desktop and mobile widths.

QR attendance, SMS/email, SIS integration, financial features, and automatic account purging remain out of scope.

## Working-tree note

This repository has accumulated related user-requested changes in one working tree. Preserve existing modifications and avoid reset/checkout commands that discard changes. Use migrations for schema changes and add regression tests with each feature.
