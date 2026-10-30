# Dashboard grouping and campus chart verification

Date: 30 October 2026

Director and Coordinator analytics now group participation breakdowns, detailed
activity reports, and supporting insights in independently expandable sections.
Admin's shared university analytics receives the same grouping. Overview metrics,
Coordinator follow-ups, upcoming activities, filters, and exports remain visible.
The Director dashboard groups its campus chart under Campus Participation.

The later dashboard follow-up, campus-coverage, and performance-layout refinements
are documented in [DASHBOARD_REFINEMENT_QA.md](DASHBOARD_REFINEMENT_QA.md).

The shared counting-explanation block is removed. Attendance-rate context and
provisional-attendance labels remain. Calculations, report scopes, exports,
historical records, and database schemas are unchanged.

## Design decisions and skills

- `kpi-dashboard-design`: preserve the summary-to-detail hierarchy and reuse the
  same filtered evidence for metrics, charts, report rows, and exports.
- `ui-ux-pro-max`: paired horizontal bars, direct count labels, patterned series,
  whole-number ticks, readable category labels, and a semantic table fallback.
- `ponytail` at full intensity: reuse the existing Jinja components, Plotly,
  native disclosures, and shared CSS without adding dependencies.
- `frontend-design`, `antislop`, `antislop-ui`, `antislop-human`, and
  `antislop-layoutmobile`: retain PSU blue and Inter typography, use spacing and
  borders to group related evidence, preserve keyboard focus and touch targets,
  and contain report-table overflow. Dials: energy 1, rhythm 2, motion 1.
- `web-design-guidelines`: reviewed the changed templates, scripts, and styles
  against the current upstream guidelines. No outstanding in-scope findings.

Native summaries include expansion indicators. Incoming fragments open their
containing sections. Targeted activity requests and pagination reveal the report;
page links preserve filters and target the report anchor. Charts render on demand
and redraw when reopened. Campus labels wrap while tooltips and tables retain
the full campus name. Zero-count campuses render separately from empty results.

## Verification

- Python: 136 dashboard, analytics, report, and pagination checks passed, plus
  33 grouping, UI structure, and responsive-table checks.
- JavaScript: four runnable chart tests passed (`node tests/charts.test.cjs`),
  covering count labels, zero/empty distinction, disclosure reopening, and errors.
- Headless Chromium: 339 browser assertions passed across Director and Coordinator
  dashboards/analytics and Admin analytics at 1440px, 390px, and 640px widths.
- Browser coverage includes Enter/Space operation, visible focus, 44px summary
  targets, independent sections, monthly/weekly switching, chart reopening,
  fragment navigation, filter submission, scoped CSV/PDF downloads, and pagination.
- Chart scenarios include empty data, all-zero campuses, one registration with
  zero attendance, equal counts, five-digit counts, and long campus names.
- Table fallbacks work with JavaScript disabled and Plotly unavailable. Browser
  checks reported no uncaught JavaScript errors in the normal page flows.
- Contrast checks passed: PSU blue on the page background 9.51:1; attendance
  color on white 6.09:1; count text on white 17.12:1; muted text on the page
  background 8.88:1.
- JavaScript syntax checks and whitespace checks passed for the changed files.

Browser QA used synthetic records in an isolated in-memory SQLite database.
The 640 × 450 viewport checks reflow equivalent to 200% zoom on a 1280 × 900
display; native browser zoom was not separately exercised.

## Antislop delivery gate

- Hard gate PASS: real report-derived counts, working native controls, visible
  focus, accessible fallbacks, explicit empty/error states, and contained overflow.
- Purpose gate PASS: PSU colors and typography preserve identity; grouping reduces
  scanning; labels and patterns make count comparisons explicit without new decor.
- Liveliness PASS: the declared dials retain the institutional summary, actionable
  follow-up queue, and expandable evidence hierarchy.
- Craftsmanship PASS: automated and browser evidence covers the changed behavior;
  no dependencies, counting changes, or unrelated workspace edits were introduced.

Guidelines source:
[Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
