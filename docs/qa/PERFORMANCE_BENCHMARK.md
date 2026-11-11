# Performance verification, 2 November 2026

The candidate is based on `c960159`. Local measurements use isolated MariaDB
10.4.32, mysqlclient, a 128 MiB database buffer pool and a five-connection app
pool. The benchmark contains 1,000 activities, 50,000 registrations, 1,000 new
volunteers, active Terms/Privacy acceptances, 30 mapped annual targets,
cancellations, incomplete attendance, notifications and historical records.
The existing presentation and performance seed commands were not changed.

## Baseline

Warmed probes of the previous code using the same policy-aware fixture:

| Workflow | SQL statements | Local elapsed |
|---|---:|---:|
| Public opportunities | 6 | 11.6 ms |
| Volunteer dashboard | 33 | 73.8 ms |
| Coordinator dashboard | 34 | 379.5 ms |
| Coordinator analytics | 31 | 347.0 ms |
| Attendance page, 50 participants | 109 | 39.4 ms |
| Director dashboard | 46 | 3,505.5 ms |
| Live analytics | 47 | 3,494.2 ms |
| Historical analytics | 48 | 3,452.4 ms |
| Annual-goal details | 27 | 4,671.8 ms |
| Notifications | 7 | 4.1 ms |
| Full CSV | 11 | 175.4 ms |
| Full PDF | 11 | 440.2 ms |

These are individual warmed probes, not p95 results or Railway measurements.
The baseline fails the planned query budgets. Query counts include policy checks.

## Final local comparison and load test

| Workflow | SQL before / after | Warmed elapsed before / after |
|---|---:|---:|
| Public opportunities | 6 / 4 | 11.6 / 6.4 ms |
| Volunteer dashboard | 33 / 16 | 73.8 / 23.1 ms |
| Coordinator dashboard | 34 / 19 | 379.5 / 102.5 ms |
| Coordinator analytics | 31 / 18 | 347.0 / 83.8 ms |
| Attendance page | 109 / 9 | 39.4 / 10.6 ms |
| Director dashboard | 46 / 21 | 3,505.5 / 601.4 ms |
| Live analytics | 47 / 18 | 3,494.2 / 368.3 ms |
| Historical analytics | 48 / 10 | 3,452.4 / 7.2 ms |
| Annual-goal details | 27 / 10 | 4,671.8 / 576.0 ms |
| Notifications | 7 / 5 | 4.1 / 5.3 ms |
| Full CSV | 11 / 6 | 175.4 / 178.5 ms |
| Full PDF | 11 / 6 | 440.2 / 544.6 ms |

The final policy-aware workload completed 12,568 requests and 1,250 writes in
1,035.37 seconds (12.14 requests/second), including the 15-minute 50-user hold.
There were zero HTTP errors, inconsistent persisted writes or duplicate
registrations. All 50 actors completed registration/cancellation/review; twenty
contenders for the last place admitted exactly one. Peak app RSS was 242.08 MiB,
74.5% below the explicit local 950 MiB budget; database connections peaked at five.
CPU time was 620.23 seconds, including local clients.

| Workflow at 50 users | p95 | Maximum SQL statements |
|---|---:|---:|
| Signed-in opportunities | 560 ms | 7 |
| Volunteer dashboard | 599 ms | 16 |
| Coordinator dashboard | 732 ms | 19 |
| Attendance page | 497 ms | 9 |
| Director dashboard | 1,400 ms | 21 |
| Live analytics | 1,147 ms | 18 |
| Annual-goal details | 1,362 ms | 10 |
| Notifications | 485 ms | 5 |
| Registration save | 1,419 ms | 13 |
| Cancellation save | 384 ms | 11 |
| Cancellation review | 399 ms | 9 |

Attendance saves used six statements in the workload. The separate 50-request
opportunities burst had 305 ms p95 while its concurrent PDF completed in 673 ms.
All measured local latency/query/headroom checks passed. The runner's JSON is at
`.qa-presentation-temp/performance-final-policies.json`; baseline and index
evidence are alongside it. These ignored local artifacts contain no live backups.

The runner uses local Werkzeug with four request slots. It checks Flask session
isolation, query growth and MySQL behavior, but does not prove Gunicorn worker
health or Railway latency/capacity. CPU includes the local client work; RSS excludes
the separate database process. Cold starts, actual hosting memory headroom and
the 30-minute Demo observation require separate Railway validation.

## Index evidence

All eight candidates were selected by the disposable MariaDB optimizer. Event
date and campus/date lists, registration history and notification order lost their
filesort; capacity, attendance, unread and throttling obtained composite coverage.
Warmed median SELECT times improved in these small local probes; this is evidence
for the plans, not a claim of a large latency gain on a small presentation dataset.
Apply, repeat application and rollback were verified on disposable MariaDB.
Rollback recreates required foreign-key support indexes before dropping owned
composites because MySQL/MariaDB can silently replace their original automatic indexes.

Actual Railway indexes still require preview/EXPLAIN review before applying DDL.
Commands, backup requirements and rollback are in
[the operations guide](../operations/PERFORMANCE_ROLLOUT.md).

## Correctness and interface evidence

Focused reporting, annual-goal, shared-target, ranking, cancellation, registration
and unchanged-fixture regressions passed in staged runs. The final 50-person save
check verifies real single SQL statements rather than hiding per-row driver loops
behind `executemany`, and verifies that records on the next page remain unchanged.
New query budgets use active policy records and cover both anonymous and signed-in
opportunities. Request-local values reflect the next committed notification update.
The final performance/loader run passed 22 tests. Startup/configuration/error/security
checks passed 79 tests; the remaining loader assertion was updated for eager loading
and then passed in that final run.

Forty browser checks cover eight paginated workflows at 1440, 900, 768, 390 and
320 pixels. Checks passed for keyboard navigation, visible focus, 44px link targets,
contained table overflow, no page overflow and unsaved-attendance protection.
No JavaScript errors were observed. No manual screen-reader or physical-device
verification is claimed.

PSU direction is unchanged: Inter, navy/blue/gold, existing spacing and native
navigation/disclosures. Antislop was applied during implementation as chosen in
the conversation, with ponytail/full, frontend-design, UI, human and mobile checks.
The current Web Interface Guidelines were reviewed for the changed UI. No new
decorative assets, animations or component system were introduced.

Five existing public-signup test failures reproduce on unchanged `c960159`:
`test_public_registration_cannot_create_privileged_role`,
`test_register_creates_user`, `test_register_accepts_prefer_not_to_say`,
`test_signup_errors_are_linked_and_retain_non_password_values`, and
`test_signup_preserves_existing_password_policy_and_records_consents`.
Do not describe the entire repository suite as green. These failures were not
removed or weakened as part of the performance work.

## Railway Demo rollout

Before rollout the Demo app was in Singapore and its database in US East; both use Serverless. A cold wake
initially refused a MySQL connection, followed by successful reads after startup.
Verified live totals: 92 accounts, 28 activities, 432 registrations and 296
attendance records. A protected dump restored into a separate recovery database;
all 37 table checksums matched. The user subsequently approved downloading the full
SQL backup to `C:\Users\arlro\Downloads\database.sql`; the downloaded 183,537-byte file
has SHA-256 `fdf717c8224ef5556b9b370c9fec7e5cd1a75d6d0682584bfa402591d8e6577f`.
No encryption of that local file is claimed. The upload archive was restored
separately: zero source upload files, 214-byte archive, matching checksums.

Runtime commit `e743b4f` deployed successfully to Demo on 2 November. The app and
attached volume moved to `us-east4-eqdc4a`, beside the stationary US East database,
within the 15-minute maintenance allowance. The deployment started at 02:36 UTC
and was successful by 02:38. The eight reviewed indexes applied with the Gunicorn
worker paused for 2.11 seconds and resumed in a `finally` block. Actual MySQL
EXPLAIN plans now use composite indexes for activity dates/campus dates, capacity,
history, attendance and notifications. The tiny auth table still chooses its old
action index; the 20,000-record disposable auth probe supports the composite for
growth. Production configuration, four gthread threads, pool limits, metrics and
email suppression were checked in the running container.

All account details matched the restored pre-change account table after migration.
There was no dataset reset. Live role-session checks returned HTTP 200 for all 17
workflows, including full CSV/PDF exports. Measured SQL counts: Admin 13, Coordinator
dashboard 19, attendance 9, cancellation review list 5, Coordinator analytics 19,
Director dashboard 21, live analytics 17, historical analytics 10, annual details 10,
goal activities 8, volunteer/history 15, signed-in opportunities 7, notifications 5,
and university exports 5. These are per-request query checks, not live p95 timings.
An additional 37 runtime/configuration/performance regressions passed. The final
live data check remained 92 accounts / 28 activities / 432 registrations / 296
attendance records, with the account table still matching its restored checksum.
Campus results remain 14/27, with Asingan 0/3 and pending evidence for Binmaley and
Infanta; university-wide targets remain separately pending at 0/3.

Twelve sequential HTTPS requests from this workstation to public Demo opportunities
all returned 200; the last ten had a measured p95 of 409.84 ms. This includes the
public edge and workstation network. Default-account role checks use temporary
internal sessions, and do not establish successful password-based login; the old
bootstrap Director password was rejected, and existing passwords were preserved.

The deployed GET-only ramps completed 173 requests at 10 users and 435 at 25 users.
The full 900-second hold at 50 distinct existing accounts completed 12,765 requests
(14.18/second). All 13,373 navigation requests and the separate default-role probes
returned HTTP 200. No connection exhaustion or worker timeout occurred in these
requests. The concurrent 50-request opportunity burst had 323.95 ms p95; a full,
valid PDF returned in 430.41 ms alongside normal navigation.

| Workflow during the live 50-user hold | Loopback p95 |
|---|---:|
| Opportunities | 33.79 ms |
| Notifications | 27.75 ms |
| Volunteer dashboard / page 2 | 61.02 / 63.99 ms |
| Coordinator dashboard | 82.14 ms |
| Attendance | 33.66 ms |
| Coordinator analytics | 74.41 ms |
| Cancellation review list | 25.64 ms |
| Director dashboard | 82.50 ms |
| Live analytics | 74.91 ms |
| Annual goals | 56.29 ms |

The service cgroup peaked at 506,118,144 bytes (482.67 MiB), with 49.4% headroom
against its measured 999,997,440-byte limit. Sampling includes the deployed worker,
probe clients and verification helpers. Cgroup CPU time increased by 201.88 seconds
over the ramps/hold; no paid capacity or services were added. Demo remained deployed
for more than 30 minutes through this observation. Raw deployed reports and resource
samples are in `/data/operations-backup-20261102/demo-*.json`.
MySQL reported a server-wide peak of six connections against its limit of 151;
that includes operator/probe connections. The deployed application pool remains
bounded at five, with no overflow.

These live loopback timings use the current presentation records and actual
Gunicorn, and exclude the public edge. They do **not** establish the 1,000-activity /
50,000-registration mixed-write Railway acceptance target. That combined case is
verified locally; production load testing and any dataset replacement remain outside
this rollout. Cold wake behavior after the new deployment is also unverified.

Main's database had no active deployment (last removed four days earlier), and
its last app build had failed before this candidate. The user explicitly requested
keeping main offline and finishing Demo first. No main code, database or service
configuration has been changed during this rollout.
