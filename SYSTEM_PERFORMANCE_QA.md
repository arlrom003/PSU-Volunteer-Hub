# System loading performance, 30 October 2026

## Measured bottlenecks and local fixes

Measured Flask requests against isolated, synthetic SQLite data: 200 events,
5,000 registrations, 4,000 attendance records and roughly 750 volunteer accounts.
Measurements compare the local workspace after the earlier report-timeout fix
with this performance pass. These are database-query counts, not hosted response
time guarantees. No original or hosted database was read or changed.

| Request | Queries before | Queries after |
| --- | ---: | ---: |
| Homepage | 18 | 5 |
| Public opportunities | 14 | 6 |
| Volunteer dashboard | 76 | 31 |
| Volunteer profile | 80 | 34 |
| Signed-in opportunities | 19 | 11 |
| Coordinator dashboard | 418 | 28 |
| Coordinator analytics | 460 | 24 |
| Director analytics, 2026 recognition | 807 | 42 |

The admin page decreased from 1,547,541 to 67,755 bytes of HTML in this fixture,
approximately 95.6% less HTML. Query count remained 12; pagination addresses the
large response and browser rendering work rather than reducing that count.

- Annual participation loads attendance and participant profiles in the same
  query, preserving campus, year, evidence basis and sex grouping.
- Recognition counts use grouped queries instead of one count per volunteer.
  Existing role, year, campus, completion, ordering and rank rules are retained.
- Forecasts and attendance summaries batch their existing counts, including their
  original treatment of cancelled registrations in the denominator.
- Recommendation history and candidate skills load in batches. Cosine scoring,
  history weighting, cold-start behavior and recommendation logging are retained.
- Homepage, opportunities, volunteer history and coordinator workspace preload
  the related records that their current templates use.
- Active users, deactivated users and activity logs load 25 rows per admin page.
  Links preserve tab/campus selection; ordering has a stable ID tie-breaker.
  Invalid pages redirect to the last available page. Deactivated-account totals
  remain global; the deactivated table now follows the selected campus filter.
- Public packaged styles, scripts, assets and the favicon use Flask's normal
  conditional caching. Browser checks observed 304 responses on subsequent
  navigations. Signed-in HTML, uploads and errors retain `no-store`.

## Verification

- 179 broader tests passed in 421.72 seconds: annual goals, opportunity journeys,
  profiles, recommendations, analytics, administration, startup, inactivity,
  coordinator follow-ups and calendars, including the initial performance tests.
- Final `tests/test_system_performance.py`: 25 passed in 12.30 seconds, including
  two additional checks of exact award counts and forecast denominators.
- Query budgets cover every role on the large fixture. Tests traverse all admin
  pages without duplicate/missing rows, preserve URL filters, exercise invalid
  pages and empty states, and retain the admin role boundary.
- Public-asset tests check conditional 304 responses with zero user queries.
  Uploads, authenticated HTML and missing assets retain their no-store policy.
- Python compilation, template formatting (`djlint --check`) and whitespace checks
  passed.

## UI design read and audit

The user chose antislop during the work. Audience: PSU administrators managing
university accounts. Keep the existing table hierarchy, Inter typography, PSU blue
`#00408b`, white surfaces, ink `#111c2c` and muted text `#424752`. Reuse native links
and existing buttons rather than adding navigation widgets or dependencies.
ENERGY 1 / RHYTHM 1 / MOTION 1. The new result count explains the current slice;
the 25-row limit reduces loading without hiding access to other records.

Reviewed the changed admin template and stylesheet against the current
[Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
No remaining findings in the changed pagination controls. Selected tabs expose
`aria-current`; page navigation has distinct accessible names and real links.

Local browser checks used synthetic accounts, not hosted sign-in sessions:

- Enter activates Next Page; first/last pages show the appropriate navigation.
- Active, deactivated and activity-log lists paginate; campus selection is kept.
- A campus with no deactivated users displays the existing empty state.
- Visible blue keyboard focus; native buttons/links remain keyboard operable.
- Desktop, 375px and 320px checks: no page overflow; navigation targets are at
  least 44px tall and wrap within the available width.
- Contrast: blue/white 9.97:1; muted text/white 9.31:1.
- No browser JavaScript errors. Existing native document navigation supplies
  loading feedback; shared error pages remain in use.

Actual browser zoom at 200%, screen-reader output and a physical phone were not
tested. The preview server and its automatic synthetic identity are local QA
scripts outside the repository; they are not application or deployment changes.

## Deployment and remaining hosted checks

This performance pass is prepared for the user-authorized push to both Git
repositories. The earlier report-timeout fix is included where it was missing.
The performance test fixture uses the existing marker-only demo command's
confirmation text, with an isolated in-memory database; the separate broader
demo-reset implementation and unrelated local security changes are excluded.
Hosted deployment completion and performance still require verification.
No dependency, schema migration, paid upgrade, Railway setting or worker-count
change was made. Existing unrelated local changes remain intact.

After deployment, compare Railway HTTP-log `upstreamRqDuration` and total request
duration for the same routes. Verify app and MySQL region/private-network settings,
then check CPU, memory and concurrency before tuning Gunicorn or hosting resources.
These hosted conditions were not measured here. See
[Railway's performance troubleshooting guide](https://docs.railway.com/deployments/troubleshooting/slow-deployments).
