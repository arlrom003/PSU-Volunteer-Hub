# PSU custom error screens

Design read: clear institutional recovery screens for visitors and all PSU roles. ENERGY 1 / RHYTHM 1 / MOTION 1.

PSU dark blue carries the code and heading; the short gold underline identifies the recovery content without carrying text. Inter, the PSU logo, and existing button styles retain the application identity. A single readable column gives priority to what happened and where to go next. No decorative illustrations, tiles, or animation are added.

## Behavior

- Global handlers cover 400, 403, 404, and 500. HTTP statuses and relevant exception headers are preserved.
- Unknown URLs and route-level errors use the shared page. Explicit JSON responses, redirects, and the specialized external-registration unavailable page remain independent.
- Requests with a JSON body/content type or a stronger JSON Accept preference receive `{ "error": "safe message", "code": STATUS }`. Wildcard Accept defaults to HTML.
- CSRF failures explain that the form expired. No raw exception descriptions appear in HTML or JSON.
- Flask logs unexpected exceptions. The 500 handler rolls back the session; rollback failure is logged while still rendering a safe response.
- Rendering bypasses account, policy, notification, and idle-session context processors. Error responses do not look up users in the security-header hook. Static assets and unknown URLs bypass account checks, allowing the recovery page to render during database failures.

## Development and production

Custom screens are the default, including local development with Flask debug/reload enabled. Set `DEV_ERROR_DEBUGGER=true` only in development to propagate exceptions to the debugger. Production forces propagation off regardless of this variable. Testing retains normal configurable propagation.

No database migration or new dependency is required. No diagnostic endpoints are added to the application; browser checks use an isolated test app.

## Verification and audit

`tests/test_error_pages.py` covers status codes, private-detail suppression, explicit JSON/redirect compatibility, CSRF, preserved headers, transaction rollback, database-failure query counts, failed user loading, static assets, and configuration overrides.

Regression verification: all 66 checks passed across error screens, production startup, idle sessions, UI structure, and role access. The Node session-script check required an unsandboxed rerun because the sandbox denied subprocess creation; that rerun passed. Python compilation and whitespace checks passed.

Browser checks exercised all four screens at 1440, 1024, 390, and 640 CSS-pixel widths (640 approximates desktop reflow at 200% zoom). All 16 combinations had no page overflow; recovery links, visible keyboard focus, 44px targets, and no-JavaScript recovery passed. OS/browser zoom on physical devices is not separately verified. Screenshots are in the session visualization folder as `psu-404-1440.png` and `psu-404-390.png`.

Contrast checks: dark blue on the existing near-white surface is 16.36:1; muted body text on that surface is 8.88:1. The existing primary buttons and new focus rings use PSU blue.

Current Web Interface Guidelines reviewed for semantic navigation, page titles/headings, skip navigation, logo dimensions/alt text, text wrapping, focus, target size, and contained layout. Recovery works without JavaScript; there is no client loading or animation dependency.

Antislop gate: Hard Gate PASS (real error codes, safe copy, working navigation, contained responsive layout); Purpose Gate PASS (brand palette/type and gold underline each serve recovery hierarchy); Liveliness PASS (one focal code, deliberate spacing, PSU identity, declared calm dials); Craftsmanship PASS for the exercised error states.
