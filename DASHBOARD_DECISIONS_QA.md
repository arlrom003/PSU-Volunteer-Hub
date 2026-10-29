# Dashboard decision support verification

Date: 29 October 2026

## Implemented behavior

- Director and Coordinator landing dashboards lead with unresolved operational work across all dates. Attendance records identify missing entries separately from present participants awaiting completion confirmation. Director links select an exact activity ID; Coordinator links open its attendance workspace.
- Director outcomes identify the actual activities and campuses needing review. Campuses without activity records are listed for the selected period. There is no total combining activity and campus issues, and no historical-data fallback in the live comparison.
- Coordinator cancellations are actionable only when requests exist. The request queue and pending attendance use oldest-first order. Upcoming activities use nearest-first order and distinguish sign-ups from remaining capacity. Existing workspace actions and security changes were preserved.
- Performance defaults to the current month through today. Presets also support last month and all dates; analytics retains custom date ranges. Explicit date URLs take precedence. Current-month differences compare the same elapsed calendar days of the previous month, capped at its last day. Custom/all-date scopes make no comparison claims.
- Attendance outcomes require an ended activity, an attendance record for every non-cancelled registration, and completed status for every present registration. Rates use summed eligible registrations, not an average of activity rates. Missing denominators and targets display an explanation instead of a zero percentage.
- The 75% attendance threshold is labelled a review guide. Target judgments require a positive whole-activity target and fully recorded attendance. Demographic subsets suppress target judgments, including target-completion percentages in exports. Unfinished activity target percentages are also withheld from exports.
- Validated attention filters apply before aggregation, pagination, and CSV/PDF generation. Exact activity IDs remain constrained by role/campus filters. Export column layouts remain compatible; metadata identifies attention and demographic scope. Existing direct export URLs without dates retain their all-date behavior; UI export links include the effective dates.
- Analytics presents findings, metrics, comparison charts, and records before supplementary evidence. Campus comparison uses paired horizontal bars with distinct patterns. Trends use categorical period axes rather than inferred timestamps. Both periods' detailed values remain available without JavaScript.

## Automated verification

- Dashboard/reporting/analytics selection: **108 passed**, 225 deselected. This run covered the revised defaults, existing report filters, campus include/exclude selection, pagination, role isolation, and exports.
- Final dashboard decision, summary, and responsive regression run: **22 passed**. Includes weighted rates, exact 75% boundary, missing versus unconfirmed attendance, ongoing/future activities, absent targets, cancellation exclusions, leap years, and shortened comparison months. Replaced the obsolete combined-attention-total test with activity-based decision tests.
- Coordinator landing/campus security selection after removing unused summary queries: **10 passed**.
- Final landing-page and ordering check, including pending and empty cancellation queues: **3 passed**.
- Python compilation, JavaScript syntax checks, four Jinja template compilations, and scoped `git diff --check` passed.

## Browser verification

Used a disposable in-memory SQLite preview on loopback port 5057. No deployment database was modified. Screenshots contain seeded test records.

- Both role dashboards and analytics inspected at mobile (390px), tablet (1024px), and desktop (1440px) sizes. Application body widths stayed within the available viewport; wide reports retained internal scrolling. The browser's injected comments overlay is outside application content and can affect root-document scroll-width measurements.
- Checked a 640 x 450 CSS viewport for reflow equivalent to a 1280 x 900 display at 200% zoom. Native browser zoom was not changed.
- Director attendance evidence and target-attention links opened the matching records. Coordinator Complete attendance opened the selected activity. Last-month selection returned the exact September reporting dates and useful empty-state text.
- Exercised keyboard Tab/Shift+Tab on period controls. Both showed a solid 3px PSU-blue focus indicator and 44px target height. Native disclosures opened with Enter.
- Switched monthly/weekly trends and opened chart-value disclosures. Categorical axes avoided sub-second timestamp labels for single-month data.
- Disabled JavaScript and verified that native detailed-value disclosures still showed report counts. Re-enabled JavaScript, deliberately blocked the Plotly library, and verified the chart-unavailable message and working value fallback. Restored script execution, networking, and viewport overrides after testing.
- Downloaded the selected Coordinator low-attendance CSV and PDF. The HTML evidence table contained the same selected activity; automated tests additionally verified both roles' filtered export datasets.
- Existing reduced-motion rules remain in place; no new animated UI was added. No destructive activity, account, or cancellation decision was submitted during browser testing.

## Design and audit gates

Reading: institutional decision dashboards for PSU extension leadership and campus coordinators. Dials: **ENERGY 1 / RHYTHM 2 / MOTION 1**.

- **Hard gate PASS:** real report counts, role-scoped records, live route actions, keyboard-operated native controls, visible empty/unavailable/error states, and measured application reflow. No invented claims, assets, navigation, or decorative animation.
- **Purpose gate PASS:** PSU blue identifies actions and focus; existing gold retains institutional identity. Inter preserves established typography. A single highlighted factual summary establishes the next action. Lists and disclosures keep exceptions readable without duplicating management controls.
- **Liveliness gate PASS:** role-specific headings, campus/activity names, evidence summaries, and deliberate spacing provide hierarchy within the existing PSU shell.
- **Craftsmanship gate PASS:** shared summaries, consistent metric units, labelled scopes and denominators, working drilldowns, export parity, and completed automated/browser checks support the changed UI.
- Contrast: main text on the new pale-blue summary **14.96:1**; PSU blue on white **9.97:1**; muted text on the main background **8.88:1**. New focus indicators use solid PSU blue.

Reviewed changed templates, chart behavior, role-guide copy, and shared styles against the current [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). In-scope fixes included 44px native period controls, visible focus, unique chart hint IDs, reachable detail anchors, explicit chart failures, non-color chart distinctions, and preserving native navigation/form behavior.

Limitations: this was not a live-data deployment or a timed comprehension study with PSU directors/coordinators. Event times retain the application's existing server-local scheduling convention. Production-scale query profiling and real-device assistive-technology testing were not performed.

## Clutter reduction revision

The follow-up revision consolidates all review reasons into one row per activity. It shows three rows initially and exposes remaining activities through a native disclosure. The Director's inactive-campus list and secondary navigation now expand on demand. Coordinator upcoming activities are limited to the next three, with the full management workspace collapsed by default and reopened when its filters are applied. On wide screens, the coordinator's current work and next activities sit side by side.

Metric definitions now share one disclosure instead of five help controls and several explanatory paragraphs. A short visible attendance denominator remains beside the metrics. Secondary analytics breakdowns and rate tables are collapsed. Charts in closed disclosures initialize when opened so they fit the available width.

Final checks for this revision:

- **23 decision, aggregation, and responsive tests passed**, including a new regression asserting that an activity with both a missed target and low attendance appears once with both reasons.
- **11 selected app regression checks passed** for role guides, filters, and report pagination/export scope. The updated metric-help assertion and dashboard-ordering checks subsequently passed in a **2-test** run.
- Jinja compilation, Python compilation, JavaScript syntax checks, and scoped diff checks passed.
- Both landing pages fit their application body within 390px, 1024px, and 1440px viewports. Reflow at 640 x 450 also retained contained widths. With the seeded fixture at 1440 x 1000, performance starts approximately 695px down the Director page and 623px down the Coordinator page, placing the metric strip on the first desktop screen.
- Keyboard Enter expanded the extra attention rows, definitions, management workspace, and supplementary chart breakdowns. Workspace filters preserved the open workspace; the exact-activity drilldown reached the matching record. Supplementary charts rendered at a measured 305px width on mobile without application overflow or browser console errors.
- Anti Slop **PASS**: one activity per queue row, compact role-specific hierarchy, existing PSU typography and colors, native disclosures, measured reflow, visible focus, and no added decoration or dependencies. Dials remain ENERGY 1 / RHYTHM 2 / MOTION 1.
- Current Web Interface Guidelines review **PASS for changed controls**: semantic links/forms, 44px targets, solid focus indicators, accessible native disclosures, contained tables, and working revealed charts. The earlier live-data and human-comprehension testing limitations still apply.

Button affordance follow-up: review, attendance, management, analytics, calendar, and supporting-workspace actions now reuse the existing outlined button component; primary actions remain filled. Navigation retains native links. In the browser at 390px and 1440px, row actions measured 44px tall with visible borders and no text underlines, application widths stayed contained, and keyboard focus showed the solid 3px PSU-blue outline. Templates compiled and scoped diff checks passed. Current Web Interface Guidelines and Anti Slop checks pass for this style-only change.
