# Annual goal dashboards

## Design read

Institutional decision support for PSU directors and extension coordinators. ENERGY 1 / RHYTHM 2 / MOTION 1.

- PSU blue carries readable numbers; gold is a short underline that identifies the primary decision metric.
- Inter retains the institutional interface and makes labels consistent with the existing application.
- One open summary composition gives goal attainment priority without tiles. Whitespace and a divider separate attendance by recorded sex from AOP/ASP attainment.
- Detailed evidence uses dedicated pages so the landing dashboard remains readable. Native links, disclosures, controls, and button styles preserve keyboard behavior.
- Sample goals are explicitly labelled, read-only presentation data; they are never inserted into the database or included in official exports. Participation in preview is separately labelled as actual records.

## Operator rollout

1. Back up the database and validate the migrations against a staging copy.
2. Apply `migrations/20261030_annual_plans.sql` if its four tables do not already exist.
3. For an existing installation, run `flask --app wsgi:app migrate-annual-goals --database DATABASE_NAME --dry-run`, review the listed changes, then omit `--dry-run`. This handles partially applied changes and automatically generated foreign-key names. The raw workflow SQL is for a database created using the named constraints in the initial SQL migration. Deploy code after schema changes. Migrations are explicit and never run automatically in production.
4. Use the director's goal workspace or the approved CSV importer. Use **Preview sample data** from either dashboard to review the design before official targets arrive.

The workflow migration adds comparison rules, active-version markers, evidence coverage, optional aggregate sex counts, explicit activity mappings, and proposal history. Existing results without reporting coverage remain evidence-pending until their approved coverage is supplied.

Local schema repair: the development database `localhost/psu_volunteer_hub` had the original annual tables without the workflow columns. The rerunnable migration added the five missing columns and changed its generated campus foreign key to RESTRICT. All annual table row counts were preserved; a subsequent dry run reported zero remaining changes. `create_all()` creates missing tables but does not upgrade columns on existing tables.

## Approved CSV import

Use `docs/annual-plan-import-template.csv`. Run `flask --app wsgi:app import-annual-plans FILE --dry-run`, review the result, then omit `--dry-run` to commit. The command uses the configured database; choose the intended environment first.

- Stable keys identify plans, indicators, targets, and result snapshots. Approved definitions are immutable. Import a new target key with `replaces_target_key` for a revision; history remains available.
- `campus_code` is blank for university targets; otherwise use an existing campus code. University targets are never distributed automatically to campuses.
- Required approval provenance: `approval_reference` and ISO `approval_date`. Plan types: AOP or ASP. Rules: `gte`, `lte`, `eq`. Values are non-negative, finite, at most 1 trillion, and at most four decimal places.
- Bases: `approved_aggregate`, `activities`, `registrations`, `verified_attendance`, `completed`, `unique_attendees`.
- Shared AOP/ASP obligations use the same `shared_key` with compatible target, rule, unit, and basis within a year and scope.
- Calculated targets use semicolon-separated `event_ids` within their year and campus scope. Imported totals cannot be added to those linked records. Ended activities require complete attendance for target judgments.
- Approved aggregate snapshots require `result_key`, `result_type=approved_aggregate`, `actual_value`, source, ISO coverage dates, and a coverage explanation. Snapshots replace earlier snapshots for assessment; overlapping snapshots are never summed.
- Optional `sex_counts` is JSON with all four keys: `female`, `male`, `prefer_not_to_say`, `unrecorded`. Values must be non-negative integers summing to the approved count. State registrations, attendance occurrences, completed occurrences, or unique people in the coverage explanation. These counts remain separate from live participation evidence.
- Dry runs and invalid files roll back the entire import. Repeating an identical file does not duplicate records.

## Permissions and interpretation

Coordinators create/edit their own campus drafts, submit them, and revise returned or approved targets. Directors review, approve, or return proposals with a reason; they can publish university goals and manage supporting evidence. Submitted/returned/draft targets never enter achievement figures. A revision leaves the old target active until approval. Shared obligations keep both plan memberships on revision.

Hero = verified targets met / all approved applicable targets. Pending evidence stays in the denominator. AOP and ASP subtotals may overlap. A campus receives **All targets met** only when it has at least one approved target and every target is verified and met. No targets is **Not available**, never zero achievement.

Sex evidence defaults to present attendance linked through non-cancelled registrations. Repeated attendance is an occurrence per activity. Completed participation also requires completed registration status. Unique attendees use recorded participant identities within scope; separate identities cannot establish institution-wide uniqueness. Not recorded remains in the denominator; ties are explicit.

## Verification

Automated coverage is in `tests/test_annual_goals.py` and the existing dashboard/reporting/responsive/startup suites. Browser checks exercise both roles at 1440, 1024, 390, and 640 CSS pixels (the last approximates reflow at 200% desktop zoom). A real device/OS zoom check and staging MySQL migration remain deployment validation steps.

Contrast: PSU dark blue `#001a41` on white is 17.16:1; PSU blue `#00408b` on white is 9.97:1. Gold conveys emphasis only. New focus indicators use PSU blue.

Web Interface Guidelines audit: semantic navigation/actions, form labels, focus, pending-submit feedback, errors, responsive overflow, URL filters, and native disclosures reviewed against the current source. Error summaries receive focus; edited goal forms warn before leaving unsaved changes. Tables retain contained scrolling, including absolutely positioned screen-reader text.

Browser verification passed 32 role/page/viewport combinations, plus a coordinator submission, director approval, approved evidence entry, resulting achievement update with CSRF enabled, and the detail view with JavaScript disabled. No page errors were observed. Desktop and mobile screenshots are saved in the session visualization folder.

Regression results: 178 checks passed in the broader dashboard/reporting/permission/UI run. Its single historical-form regression was corrected by keeping the goal-year form on landing pages and keeping the historical-only view separate; the subsequent focused run passed all 27 goal, dashboard-decision, and historical-reconciliation checks. Python compilation and JavaScript syntax checks passed. New MySQL table DDL compiles with the MySQL dialect; migrations have not been applied to a staging or production MySQL database during this session.

Antislop gate: Hard Gate PASS (labelled sample figures, native working controls, visible focus, contained mobile overflow); Purpose Gate PASS (blue number, gold underline, and separated participation each serve the stated hierarchy); Liveliness PASS (one numeric focal point, PSU palette/Inter, deliberate whitespace, ENERGY 1 / RHYTHM 2 / MOTION 1); Craftsmanship PASS for the exercised local states and workflows. Deployment validation remains as described above.
