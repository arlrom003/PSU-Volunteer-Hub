# PSU Volunteer Hub — UX, Analytics, and Administration Roadmap

## Purpose and delivery order

This roadmap improves the current Volunteer Hub while keeping the first releases aligned with the manuscript: volunteer profiles, activity posting and registration, attendance and participation history, milestone transparency, recommendations, descriptive analytics, and PDF/CSV reports. The work is ordered to improve the public and volunteer experience first, then the reporting experience, then governance extensions.

The working tagline is: **“Serve with purpose. See the impact.”**

Use clear Filipino-English wording where it improves comprehension, but retain English labels for institutional reports and data fields. Replace the volunteer-facing word **Register** with **Join Now**; keep `Registration` as the internal data term.

30 October addition: the guarded `reset-and-seed-demo` command replaces
marked demonstration records while preserving existing accounts/passwords.
Generates 750 participating internal volunteers, 200 events, 5,000 registrations,
4,000 attendance, 200 external volunteers and 150 cancellation requests. Uses
existing campus/catalogue/schema data; synthetic demographics are illustrative.
Isolated CLI/import/provisioning checks: 15 passed in 27.58 seconds. See
`DEMO_DATASET_QA.md`. Publication of this command is authorized to `thesis/main`;
hosted deployment and database execution remain unverified. Earlier deployment
results below do not cover this command; unrelated local changes are excluded.


## Latest delivery status (23 October 2026)

Publication follow-up: the user approved commit/push of the test reconciliation
and documentation. Local/no-publication statements below are verification-time
snapshots; confirm publication against GitHub main. No deployment or live-database
change is included.

23 October test-only follow-up: the three baseline failures were reproduced, then
replaced with scoped form/table assertions and destination-specific filter checks.
Matching and excluded fixtures verify rendered pages and complete CSV/PDF datasets;
profile cases cover completed/present versus pending, cancelled, absent, excused
and missing attendance within the five-record limit. No production UI, report
behavior or query format changed. Focused checks: **97 passed in 233.32s**, plus
**3 dashboard checks in 0.35s**. Final full suite: **458 passed in 1141.90s**, zero
failures/errors/skips. All three baseline assertions are reconciled and the
automated suite is green. See REGRESSION_RECONCILIATION_QA.md.
No live database access, deployment, commit or push.
Actual zoom, screen-reader and physical-device verification remains unfinished.
All earlier implementation/publication counts below are historical snapshots.

### Earlier delivery snapshots

Publication follow-up: the user approved commit/push of the opportunity journey
and registration/cancellation work in this revision. Local/unpublished notes below
are delivery-time snapshots. The 450-pass/3-baseline-failure result remains the
latest full verification; publication does not resolve those failures or the
manual zoom/device checks. No deployment or live-database change is included.

Latest local refinement: My registrations now links to activity details and shows
effective cancellation deadlines, distinct request/registration states and private
decision disclosures. Shared PSU guards align dashboard actions with attendance,
deadlines and the approved one-request rule. Form validation retains values and
supports no-script recovery; context returns to the registration record. See
REGISTRATION_CANCELLATION_UI_QA.md for current verification. No publication, new
routes/schema/dependencies or live database changes; prior journey work preserved.
Final focused verification: **66 passed in 165.81s**, including shared UI structure.
Final uninterrupted full suite: **450 passed, 3 known baseline failures in
1130.79s**, without sandbox/process/temp-file errors. All 37 new registration UI
cases passed. The existing two Director assertions and profile-cell assertion
remain a separate release gate; the full suite is not yet green.

Earlier opportunity-only iteration: public dedicated details, filtered listing counts
and Back links, plain registration states, authenticated review summary, inline
consent errors and activity-specific confirmation are implemented. Existing
joining/restoration, agreement versions and server guards remain authoritative.
Focused journey/filter checks: **43 passed in 111.42s**. See
OPPORTUNITY_JOURNEY_QA.md for full regression results and browser evidence.
Full suite: **413 passed, 3 failed in 1033.25s**. The same three failures reproduce
on committed baseline 21a0545: two Director report-filter assertions and one
profile responsive-cell markup assertion. No new journey failures were observed;
the full release is not yet green. Six shared UI checks also pass.
Not committed/pushed; no original-database writes or deployment. Prior publication
approval applies to the earlier release, not this newly requested implementation.

Consolidated release: all current application changes are approved for commit
and push after documentation updates. See RELEASE_2026_10_22.md for the exact
scope, focused checks and exclusions. Current isolated publication selection:
**106 passed in 260.39s**, zero failures. Coordinator baseline 8c22e5f is already
in main. Older local/uncommitted and pending notes below are historical snapshots.
The combined revision includes the auth remake, session-only/inactivity behavior,
PSU-sign-in-only public joining, signed-in Help, Director view context, policy
source files, Docker preparation and backup/restore documentation. No live policy
publication, database changes or Railway deployment is included.

Next unfinished verification: reconcile the three baseline report/profile
assertions, plus actual browser zoom/screen-reader/physical-mobile checks. The
393-pass full run is the 21 October snapshot; do not relabel it as today's
combined-revision full run. The latest 413-pass/3-failure result above supersedes
the previously pending combined-suite check.

22 October Coordinator operations refinement: authenticated record tables now
reflow into labelled mobile records while dense reports use labelled internal
horizontal scrolling. The Coordinator activity workspace prioritizes attendance,
groups routine secondary actions in a native disclosure, and keeps removal
separate. Attendance has a quick activity picker, timing guidance, roster totals,
native-confirmed bulk controls, and a mobile save bar. Create Activity now stages
core details and volunteer requirements before optional settings. No route, schema,
dependency, authorization, export, or live-database change was made. Focused
responsive-table checks passed 4 tests; focused Create Activity checks passed 5.
Temporary local previews verified desktop, 390px mobile, and a 200%-equivalent
narrow viewport.

21 October local inactivity work: user selected 30 minutes / 1-minute warning.
Shared server expiry and native warning added across role/public/auth layouts,
with CSRF-protected renewal and an explicit inactivity sign-in message. Final
20 focused checks and 7 Node checks passed, plus isolated role/mobile/keyboard/
multi-tab browser checks. Final uninterrupted full suite: **393 passed in
986.10s**, zero failures. See SESSION_IDLE_QA.md for evidence and limitations.
No migration, live DB write, cloud change or publication.
The prior uncommitted login/signup remake and deployment preparation are retained.

21 October Railway follow-up: local image build, network-isolated Gunicorn and
synthetic SQLite/public/private file persistence passed; 18 Linux tests passed.
See DOCKER_DEMO_QA.md. Actual Railway allowance/services/MySQL/HTTPS checks and
publication remain pending. Original database never accessed by container tests.

Railway thesis-demo preparation (local): Dockerfile/context allowlist and deployment
checklist added; 20 focused checks passed. No Docker engine running locally, so
image build/runtime and actual Railway deployment remain unverified. Trial account
allowance and two persistent volumes must be checked before creation. No cloud
writes, publication, original database changes or paid upgrade.

Latest local recovery work: native MariaDB backup/restoration passed on a new
disposable target, all 31 schema/1,167 row hashes and 2 public upload hashes
matched. Original unchanged. See BACKUP_RESTORE_RUNBOOK.md and BACKUP_RESTORE_QA.md.
Not complete production DR: private files absent, no encrypted off-site copy,
independent-host recovery or scheduled backup/alert verification. No publication.

Publication follow-up: verified production initialization, tests and QA documents
are approved for commit/push. Earlier local/publication-pending notes below
describe implementation snapshots. Deployment gates remain open.

Production initialization release gate: full suite **352 passed in 885.51s**
in one run; scoped diff reviewed. Actual disposable MariaDB setup/login/repeat
checks already passed. Ready for commit/push approval, not yet published.
See PRODUCTION_INIT_QA.md. No live database changes or deployment.

Latest local work: explicit production initialization command now creates the
current schema, reference data and first Admin in a confirmed empty target only.
No demo users/events, no startup auto-writes, no existing-database modification.
SQLite regression coverage added; actual MariaDB provisioning, full regression,
hosting/recovery checks and publication remain pending. See README and HANDOFF.
Focused provisioning/startup/app-init/historical-import verification: 24 passed.
MariaDB follow-up completed on a new disposable target: reference data and one
working Admin only, repeat refused, original all-table fingerprints unchanged.
See PRODUCTION_INIT_QA.md. Full suite, publication and hosting gates still pending.

Publication revision: production startup safety, tests and SQL tracking removal
are approved for commit/push. The local/staged notes immediately below are prior
implementation snapshots. Local dumps retained; history remains unchanged.

SQL export cleanup, local only: the two full dumps are staged for removal from
Git tracking, with byte-identical local copies preserved and ignored. README
and Database/README.md document safer setup and remaining schema/provisioning
work. No history rewrite, commit, push, account changes or live database changes.

Latest local deployment-safety work (not committed/pushed): production startup
now skips schema creation and automatic seeding. Explicit `wsgi:app` selects
production; default factory respects APP_ENV; direct app.py rejects production
development-server use. 12 startup/app-init checks passed in isolated SQLite.
Existing databases unchanged. Provisioning, tracked SQL/history exposure,
backup/restore and actual hosting verification remain release gates.

Publication revision: the user approved commit/push of both verified repairs,
tests and documentation. Earlier pending/uncommitted statements below are dated
implementation snapshots; final verification is recorded in REPAIR_RELEASE_QA.md.

Follow-up, 20 October 2026: cancellation Approve/Reject submission repaired locally
in the shared loading-state script. 18 backend/UI checks and 6 JavaScript checks
passed; browser desktop approval/mobile keyboard rejection passed in isolated
SQLite with CSRF. MariaDB-copy rerun is pending (server stopped).
Future-attendance completion is now also repaired locally: server timing guard,
opening-time notice, and disabled controls before end (legacy start fallback).
Final timing/cancellation/UI run: 22 passed; broader attendance/UI run: 56 passed,
plus one added external timing case. Full suite and copied-MariaDB verification
are the next unfinished gate. Neither repair is committed/pushed.
See CANCELLATION_REPAIR_QA.md and ATTENDANCE_TIMING_QA.md.

Approved refinement, 20 October: allow check-in from 30 minutes before start,
but keep participation Confirmed and certificate-ineligible until the coordinator
saves final attendance at/after effective end (start fallback for legacy no-end
activities). This replaces the end-only attendance-write rule above.

Release verification follow-up, 20 October: copied-MariaDB browser gate completed
for both repairs, including early check-in to final attendance on one registration.
See REPAIR_RELEASE_QA.md for automated results and environment-related reruns.
Original database connections read-only; no source QA records. No commit/push.

This section records the work completed in this chat. The phases below retain
their broader requirements; a phase is not fully complete merely because one
of its screens was repaired. Items without an explicit completion status are
requirements to verify, not new claims of implementation.

| Workstream | Status | Delivered evidence |
| --- | --- | --- |
| Director and Coordinator dashboards | Completed | Shared PSU role shell, consistent headings/metrics, scoped comparisons, target progress, and real workspace links. |
| Director and Coordinator analytics | Completed for the redesign scope | Shared filtered report rows power live KPIs, comparisons, trends, pagination, and exports; historical and independently scoped evidence remain labelled. |
| Shared information tips | Completed | Reusable native disclosure macro explains KPIs, charts, reports, forecasts, recognition, and filter scopes without adding icons to every cell. |
| First-use walkthroughs for all four roles | Completed | Shared modal/spotlight tour, mobile coach sheet, keyboard controls, account-specific dismissal, Help replay, and safe handling of unavailable anchors. |
| Volunteer profile repair | Completed | Read-only identity, bounded photo, independent interest/skill choices, truthful participation counts, informational milestones, linked recommendations, and five-row history. |
| Profile validation and photo recovery | Completed | Inline errors preserve submitted choices; full validation precedes preference changes; failed saves roll back and clean new files; old photos are deleted only after successful commits. |
| Continuation documentation and UI/UX workflow | Completed | HANDOFF.md contains the current workspace, required skills, preservation rules, verification results, and instructions for a new chat. |
| GitHub delivery | Published | Commit `8745ec4` on `main` includes dashboards, walkthroughs, profile repair, tests, and handoff. This roadmap refresh is a subsequent local documentation update until committed. |
| Follow-up correctness and session fixes | Completed locally, uncommitted | Joining consent/start-time checks, safe sign-in/policy return destinations, homepage completion timing, and separate self/other Admin reset handling. Full isolated suite: 277 passed. |
| Opportunities campus filtering | Completed locally, uncommitted | Alphabetized include/exclude campus checkboxes, retained query filters and pagination, native no-JavaScript operation, and recoverable validation. 49 focused checks passed; see CAMPUS_FILTER_QA.md. |
| Coordinator operations and responsive tables | Completed locally, uncommitted | Staged Create Activity form, attendance workspace, separated activity actions, labelled mobile record tables, and contained report tables. No schema or route change; 9 focused checks passed across the two feature sets. |

### Verification recorded in this chat

- [x] Existing volunteer feature tests: **9 passed**.
- [x] Final-code profile tests: **19 passed**. Coverage includes selected values,
  missing/unknown catalog choices, validation-state preservation, unavailable
  catalogs, role isolation, JPEG/PNG/WebP, size/content/dimension rejection,
  replacement/removal, failed-commit recovery, safe cleanup, and milestone eligibility.
- [x] Earlier baseline full suite: **227 passed, 1 known failure** (228 collected). The separate
  final-code profile run includes additional edge cases added during verification.
- [x] Full suite after follow-up fixes: **277 passed, zero failures** (277 collected).
  Includes the final profile edge cases and new joining, safe redirect,
  completion-time, and Admin reset/session regression cases. Test data remained
  isolated SQLite; Windows temporary-folder permissions required an unsandboxed
  run with a dedicated test directory. No live MySQL data was changed.
- [x] Desktop, tablet, and 390px mobile inspected; keyboard controls, information
  tips, real links, long account names, and contained history scrolling exercised.
- [x] Contrast checked for new selection, checkbox-edge, error, and muted-text pairs.
- [x] Preview/test data stayed in isolated SQLite databases and temporary upload
  directories. No live MySQL data was seeded or changed by this repair.
- [x] No profile migration, framework, runtime dependency, or profile JavaScript added.
- [x] Resolve the former `TestAdminUserManagement.test_admin_reset_password`
  failure. Self-reset now signs out explicitly and explains that the new password
  is required. Separate self/other reset tests preserve session invalidation and
  verify remember-cookie cleanup, audit actors, validation, and CSRF.

Detailed evidence and limitations: `DASHBOARD_REDESIGN_QA.md` and
`PROFILE_REPAIR_QA.md`. Native OS screen-reader output, actual browser 200% zoom,
and a physical mobile keyboard were not independently verified. A narrow CSS
viewport reflow check must not be described as actual browser zoom verification.

### Required UI/UX workflow for subsequent work

- Read `HANDOFF.md` first and inspect actual local changes before editing.
- Read and apply **Ponytail (full)** for minimal, maintainable implementation.
- Apply **Anti Slop** and **antislop-ui** during implementation; complete the
  delivery gate with concrete evidence.
- Use **frontend-design** for deliberate hierarchy, typography, spacing, and composition.
- Use **antislop-human** for contrast, semantic controls, keyboard focus, and states.
- Use **antislop-layoutmobile** for responsive reflow, 44px targets, and overflow.
- Use **web-design-guidelines** to review the completed interface and report limits.
- Reuse Bare CSS, the single `base.css`, `role-shell.css`, role stylesheets,
  shared sidebar, and local PSU assets. Retain ENERGY 1 / RHYTHM 2 / MOTION 1.
- Preserve existing dashboard/profile improvements, Flask routes, CSRF, role/campus
  boundaries, MySQL schema, and cosine recommendations unless a new request
  explicitly changes them. New chats must not automatically push or alter live data.

## Phase 1 — Landing page, discovery, and joining

Implementation update, 18 October 2026: the first-use guide is now a shared role-aware spotlight tour for Volunteer, Coordinator, Director, and Admin. Completion, Skip, and Escape persist per account; Help can replay the appropriate dashboard guide using `?tour=1`.

- Rebuild the public home page as a content-driven landing page with: a PSU volunteer image hero, the tagline, clear sign-in and Browse Opportunities calls to action, a small feature section, upcoming events, recent completed activities, and help/contact links for non-technical users.
- Use approved PSU images when supplied. Until then, show existing coordinator-uploaded event cover images and milestone photos; cards without an image use the present accessible fallback artwork. Do not add unlicensed stock photos.
- Add a featured-events carousel from the nearest upcoming activities. Each slide shows cover image, title, campus, category, start and end date/time, remaining slots, and a **Join Now** action.
- [x] Replace the earlier preview-modal proposal with the approved dedicated public activity-details page. Show schedule, location, skills, SDGs, capacity, cancellation deadline and requirement notices; keep agreement bodies in authenticated consent. Joining returns to details with confirmed registration state and My registrations. Retired public guest joining stays retired; coordinator external-participant records remain unchanged.
- [x] Refine opportunities into compact image cards with linked titles, accurate filtered counts, wrapping filter summaries and distinct empty states. Preserve chronological ordering, nine-item pages, category/search and native campus inclusion/exclusion; show secondary facts on details. No card-lift motion or JavaScript-only filtering.
- [x] Campus-filter portion: alphabetized native checkboxes support multiple
  campuses with include/exclude modes, retain search/category selections through
  pagination, and work with scripts blocked. No selection shows all campuses;
  original single-campus URLs remain valid. This does not claim completion of
  every other discovery-page enhancement in the broader requirement above.
- Make the homepage’s historical-activity summary clickable. It opens a paginated historical-activity list with title, unit/campus, activity type, year, aggregate participant count, source information, and any available details. Historical aggregates remain separate from live events.
- Add completed-event story cards below the upcoming section. They are generated from finished live events and their milestone uploads, showing the event date range, completion status, featured image, and a details modal/page; no separate editorial article workflow is introduced in this phase.
- Add an application-wide loading state for form submissions and data-driven navigation: disable the submitting control, show a labeled spinner, retain keyboard focus, and restore controls after validation errors. Do not use an indefinite blocking overlay for ordinary page loads.
- [x] Replace the static guide with a shared role-aware first-use walkthrough for Volunteer, Coordinator, Director, and Admin. Native modal dialog, spotlight, step controls, mobile coach sheet, and stable real-section anchors explain the relevant workflow. Finish, Skip, and Escape persist dismissal per account. Help replays the role dashboard tour with `?tour=1` without clearing saved state. No new migration is required beyond the existing first-use timestamp field.
- Add an always-visible Help link to the public navigation and role sidebar. The help page explains signing up, profile interests/skills, joining, cancelling, attendance, recommendations, and who to contact for account issues.

## Phase 2 — profile, registration, and coordinator controls

- [x] Refine My registrations and cancellation without replacing the dashboard:
  linked activity titles/recommendations/schedule, effective deadlines, separate
  decision states, private notes, consistent availability, accessible error recovery
  and one request per PSU registration. See REGISTRATION_CANCELLATION_UI_QA.md.

Profile repair completed in this chat:

- [x] Reuse shared role header, spacing, buttons, information tips, and table components.
- [x] Show actual name, email, campus, and volunteer type; keep account details read-only and remove the unconditional verification claim.
- [x] Bound the profile photo to 96px with consistent cropping and the local `temp_profile.jpg` fallback.
- [x] Separate labelled interests and skills into native checkbox grids with visible checked/focus states and at least 44px targets. Preserve independent catalog choices and stored selections.
- [x] Keep one primary Save profile action; show separate photo removal only when an image exists. Disable saving and explain when a required catalog is unavailable.
- [x] Validate all choices and the optional image before changing stored selections. Invalid submissions retain submitted choices and show relevant inline errors.
- [x] Preserve the 3 MB JPEG/PNG/WebP rules, verify image content, reject unsafe dimensions, roll back failed database saves, and safely remove new failed-upload files. Delete previous photos only after successful commits.
- [x] Label all registration records as Registrations. Show verified present attendance separately from completed participation, which requires completed status plus present attendance.
- [x] Keep existing level/badge thresholds, using verified completed participation for count-based milestones. Explain that profile milestones are not Director recognition. Category history remains based on verified present attendance.
- [x] Remove the duplicate read-only skills panel. Make cosine recommendations navigable and link the five-row recent history to the registrations dashboard.
- [x] Keep profile CSS in `volunteer.css`, without another foundation stylesheet or additional profile JavaScript. No database migration is required.

Remaining or previously specified Phase 2 requirements follow; the profile repair
does not claim to complete every coordinator or account-management feature here.

Coordinator workflow refinement completed locally, 22 October 2026:

- [x] Stage Create Activity into operational details, volunteer requirements, and optional settings without changing form contracts, server validation, or campus ownership.
- [x] Keep routine activity actions in a native More actions disclosure and retain a separately labelled removal action with confirmation.
- [x] Make attendance an activity-first coordinator workspace with timing guidance, roster counts, browser-confirmed bulk status changes, and a safe mobile save bar.
- [x] Reflow authenticated operational tables into labelled records on small screens while preserving dense report tables inside labelled scroll regions.

- Convert volunteer skills and interests to controlled multi-select choices backed by the existing `Skill` and `Interest` catalogs. Require at least one interest and one skill at account creation and profile update; do not create free-text categories from volunteer input. Display an explanation that recommendation quality depends on profile and participation data and that results are decision support, not guarantees.
- Improve password entry with a show/hide control, a strength checklist, confirmation field during account creation or password reset, and server-side validation. Preserve the administrator-configured minimum length and reject passwords that fail the chosen policy.
- Add an optional profile image upload with validation, a generated unique filename, image type/size checks, and a default avatar. Display it in the sidebar and volunteer profile. Deleting a user removes the associated image safely.
- Extend `Event` with `cancellation_deadline` (`DATETIME`, nullable). Coordinators must set a deadline before the event start when creating or editing an event; the UI may offer a quick preset such as “2 days before” but saves the actual deadline. Volunteer cancellation is allowed only for eligible statuses before that deadline. Show the deadline in the event preview, Join confirmation, dashboard registration list, and cancellation confirmation.
- Keep existing event start and optional end dates, but make both date/time inputs explicit in coordinator create/edit forms. Validate that end is after start and that cancellation deadline is before start.
- Add coordinator announcements per event: **last call**, **event update**, and **cancelled/postponed**. Publishing an announcement creates in-app notifications for active registered PSU volunteers and shows it in event details. This uses no SMS or email integration.
- Record the uploading coordinator and timestamp for event covers, milestones, historical imports, and administrative bulk imports. Show that provenance in coordinator/admin management screens and event transparency details.
- Replace the Activity Categories text **Remove** control with an accessible icon-only **×** button, retaining confirmation, tooltip/accessible name, and the existing reassignment-to-General behavior.
- Keep QR attendance as a documented standby item only; do not add QR generation, scanning, or check-in flows in this roadmap release.

## Phase 3 — descriptive analytics and reports

Implementation update, 18 October 2026: Director and Coordinator dashboards/analytics now use shared institutional components and accessible info tips. Live comparison charts, trends, summary metrics, pagination, and downloads share the filtered report rows. Historical aggregates remain in a labelled source section; supplemental recognition, profile, and readiness panels state their own scope. The Director live activity table retains ten rows per page.

Current implementation note: descriptive analytics, PDF/CSV reporting, historical aggregate views, and an idempotent local `seed-demo-analytics` fixture are implemented. The fixture supplies representative live events, registrations, and attendance for panel demonstrations; it does not alter deployment data unless the command is explicitly run against that database.

Director demographics, SDG tagging, and annual recognition were already implemented. Apply the applicable documented migrations to an existing MySQL database before enabling those features; do not blindly rerun migrations that are already applied. Declared sex values are `Male`, `Female`, and `Prefer Not to Say`; legacy missing data remains `Not recorded`. The implementation uses the official 17-SDG catalogue and keeps historical aggregates out of demographic and recognition calculations. This chat's dashboard/profile repair introduces no schema change.

Dashboard and analytics redesign completed in this chat:

- [x] Reuse shared Jinja heading/KPI/chart macros and the existing PSU sidebar/top bar, with a skip-to-content link.
- [x] Director dashboard: university summary, campus comparison, scoped target evidence, and real analytics/calendar links.
- [x] Coordinator dashboard: Create Activity action, campus summary, upcoming workspace, targets, pending cancellations, and recent registrations.
- [x] Director/Coordinator analytics: consolidated filters/exports and a single filtered live KPI strip; compatible comparisons, composition/trends, and supporting operational evidence remain role-appropriate.
- [x] Use `app/dashboard.py` and the existing report rows to align live metrics/charts with the filtered report. Preserve filter query parameters in pagination and CSV/PDF downloads.
- [x] Retain the ten-row paginated Director live activity report. Keep historical source panels separate rather than silently treating aggregate participants as unique accounts or verified live registrations.
- [x] Label independently scoped recognition, profile-demographic/affiliation, readiness, and snapshot evidence rather than implying it all shares the live report filter scope.
- [x] Add accessible information tips and text/table chart fallbacks; preserve existing Plotly behavior, routes, authorization, and campus isolation.

The original analytics enhancements below remain a requirements checklist, not a
claim that every drill-down, search, multi-select, or multi-year feature was added.

- Keep analytics limited to descriptive reporting defined by the manuscript: counts, percentages, means, attendance/sign-up conversion, participation by campus/category/demographic, activity performance, and weekly/monthly trends. Do not expose K-means segmentation or ANOVA in the user interface.
- Move role-appropriate KPI summaries to the top of analytics pages. Make each event-count KPI clickable and route it to the corresponding filtered event/report list; for example, a summary of 50 events opens that 50-event filtered list.
- [x] Display the Director Live Activity Report in ten-row numbered pages while retaining filters.
- [x] Add literal case-insensitive activity-name search to Director/Admin and Coordinator live reports, aligned with live metrics, charts, pagination, and PDF/CSV exports. Coordinator campus isolation is retained. See ACTIVITY_SEARCH_QA.md.
- [ ] Separately assess the proposed additional View all interaction; existing Director pagination remains ten rows per page and exports already contain all matching rows.
- Add date range plus multi-year comparison controls. A user may choose one or more years; comparisons use the same selected campus, category, and activity-name criteria. If a same-named activity has no comparable data, show an explicit empty state rather than inventing a match.
- [x] Director/Admin live analytics: alphabetized multi-campus include/exclude control with consistent totals, charts, pagination, and exports. Coordinators remain restricted to their own campus. Historical/affiliation scopes remain separate; only existing catalog campuses are selectable. See ANALYTICS_CAMPUS_QA.md. No academic-unit data model was added.
- Let users change supported visualizations where the metric is compatible: line for time series, bar for comparisons, and pie/donut for composition. Preserve a text/table equivalent for accessibility.
- Add Plotly chart controls for zoom, reset, and exporting the active chart image. Retain current PDF/CSV report exports for the filtered report as a whole; do not attempt browser screenshots as official reports.
- Label historical imports as aggregate records and show a short data-quality note: historical counts cannot produce individual attendance, demographics, or precise event dates not recorded in the source. Add the same limitation to analytics export metadata.
- Keep the repeatable `seed-demo-analytics` fixture for local development and panel demonstrations. It creates representative events, registrations, and attendance without modifying real deployment data unless explicitly run there. Historical aggregate imports remain separate through `import-historical-activities`.
- Director Analytics includes a sex filter/table based on verified PSU attendance and an SDG filter for live activity reports. `Prefer Not to Say` is a declared response; `Not recorded` is a separate legacy missing-data state.
- Coordinators select one or more applicable official SDGs while creating or editing an activity; Director PDF/CSV exports and the live report display those tags.
- Director Analytics includes an informational calendar-year Top 5 for volunteers and campuses. Volunteer order is verified present attendance then completed activities; campus order is verified attendance rate then verified present attendance. Equal scores share a displayed rank. This is decision support only and excludes outsiders, cancellations, absences, unverified records, and historical aggregates.

## Phase 4 — administration and governance extensions

Current implementation note: the administrative activity log, safe CSV user import/export, and versioned Terms of Use acceptance are implemented. The remaining governance enhancement is any broader administrative policy workflow beyond the currently published Terms of Use revisions.

- Add CSV bulk-user import and export. Import uses a downloadable template, validates all rows before committing, reports row-level errors, hashes passwords server-side, and honors the existing role/campus constraints. Export excludes password hashes, tokens, and other secrets.
- Add an append-only activity log with actor, action, target type/id, timestamp, and a concise metadata summary. Record account actions, role changes, category changes, event create/edit/delete, attendance updates, milestone uploads, announcement publication, historical imports, and bulk-import outcomes. Admins can filter and export the log; coordinators see only records within their campus.
- Add versioned Terms and Conditions managed by an administrator. A published revision has title, body, version, publisher, and publication timestamp. New registrations and existing users on their next sign-in must accept the current revision before continuing; record user, revision, and acceptance timestamp. Do not retroactively invalidate attendance or historical registrations.
- Add a migration for profile images, event cancellation deadlines, announcement records, upload provenance, activity logs, and terms acceptance. Backfill upload provenance as unknown where the historical record lacks an actor. Existing events retain a null cancellation deadline and continue to use their start time until a coordinator sets one.

## Phase 5 — policy, agreements, cancellation review, and accomplishment management

Current status: implemented locally. The policy lifecycle migration, authorization checks, notifications, dashboard calendars, accomplishment reporting, and regression coverage are ready; apply the documented migration before using them on an existing MySQL database.

- Add distinct Terms of Use acceptance and Privacy Notice acknowledgement to account registration. Record each document version and timestamp separately; never combine the two acknowledgements into one checkbox.
- Require a versioned Event Participation Agreement for every event registration. Store acceptance on the registration record, not only on the volunteer account, so each event remains auditable.
- Let coordinators configure an optional event-specific NDA, including its text and version. Require NDA acceptance only after the participation agreement. Cancelling a registration must never invalidate a previously accepted NDA or prevent a volunteer from requesting cancellation.
- Replace direct volunteer cancellation with a cancellation-request workflow. A volunteer chooses a structured reason (medical/health, family emergency, academic conflict, work/schedule conflict, transportation problem, personal emergency, or other); `Other` requires an explanation. A pending request leaves participation registered until reviewed.
- Add campus-scoped coordinator review for cancellation requests with pending, approved, and rejected filters; reviewer note; reviewer identity; and review timestamp. Approval changes participation to cancelled. Rejection keeps it registered. Preserve every request and decision as an audit-relevant record.
- Reuse the existing notification service to alert coordinators about new requests and volunteers about submission, approval, or rejection. Do not create a second notification system.
- Extend event list filters for coordinator activity management: Active by default, with Upcoming, Completed, Cancelled, and All options plus category, date, campus, and department where data exists. Replace vague `Unavailable` labels with disabled actions and accessible supporting text that explains why the action cannot be used.
- Add a list/calendar switch for activities. The calendar supports monthly navigation, status, campus/department, date range, and event details; list filters should apply where practical.
- Add optional activity targets: target participants, verified actual participants, and safe target completion percentage. For completed events, actual participants must be verified attendance—not registrations. Clearly label registrations for upcoming/active activities.
- Reorder Coordinator and Director dashboards around accomplishments: KPI cards, charts, targets, actual participants, activity/campus comparisons, and supporting lists. Add a simple role-appropriate volunteer dashboard visualization without exposing coordinator/director analytics.
- Introduce centralized, data-driven campus acronyms for compact director comparisons, while retaining full campus names in reports, details, tooltips, and accessible labels.
- Test agreement/NDA acceptance, every cancellation boundary and role scope, audit retention, notification recipients, target calculations including zero targets, and the distinction between registrations, attendance, absence, cancellation, and actual participants.

## Interfaces and safeguards

- New public/volunteer views: event details/preview, historical activity list, help page, and terms acceptance page.
- New protected actions: profile image upload/remove, event announcement create, terms publish, terms accept, CSV user import/export, and activity-log listing/export.
- All state-changing forms use the existing CSRF protection, role checks, server-side ownership checks, input validation, and explicit success/error notices.
- Enforce image file allow-lists and size limits; never serve user-selected filesystem paths directly.
- Preserve role boundaries: volunteers cannot access analytics or other users’ records; coordinators remain campus-scoped; directors remain read-only; administrators retain user/configuration governance. Admin analytics remains hidden from navigation as currently requested, even though its implementation remains intact for possible panel restoration.

## Verification and acceptance criteria

- Test desktop and mobile landing pages, keyboard-accessible carousel/modal behavior, empty states, image fallbacks, readable contrast, and loaders for successful and failed submissions.
- Test guest Join Now redirects back after sign-in, volunteer registration/re-registration, outsider registration, capacity checks, start/end-date validation, and each cancellation-deadline boundary.
- Test controlled skill/interest selection, password validation, profile image validation/removal, first-use guide persistence, and recommendation limitation copy.
- Test all analytics filters together: alphabetical campuses, include/exclude campuses, multi-year comparison, first-ten/View all, KPI drill-down, chart type switching, chart image export, and report export with unchanged role scoping.
- Test historical versus live data separation and the simulated fixture in an isolated development/test database.
- Test CSV import validation/atomicity, safe export columns, audit-log completeness and access control, terms re-acceptance after a new publication, and announcement recipients.
- Run existing authorization, event, volunteer, coordinator, admin, analytics, and UI-structure tests; add coverage for every new endpoint, migration backfill, and destructive action.

## Defaults and exclusions

- The first implementation focus is public/volunteer UX, followed by analytics, then administration extensions.
- Images are PSU-approved or system-uploaded only; placeholders remain until approved images exist.
- Event stories are derived from completed events and milestone uploads, not manually authored news articles.
- Cancellation is controlled per event by an explicit deadline, with a quick two-day preset available to coordinators.
- QR attendance, automated certificate generation, additional email/SMS integrations, SIS integration, GIS, financial features, and automated account purging remain outside this chat's delivery scope. This exclusion does not remove existing email-dependent registration or password-reset behavior.
