# Volunteer profile account settings

Implemented on `codex/volunteer-profile-settings`, based on `a9694e5`.
The user authorized publishing this feature branch to both configured repositories.
The initial delivery did not deploy the feature. On 11 November 2026 the user
authorized the live merge: Demo's watched `codex/performance-workflows` branch was
fast-forwarded to `97ba1aa`, and Railway confirmed successful deployment
`fa40b10b-bba6-4208-b721-16295700b402` at `https://www.psuvolunteerhub.tech`.
No live credentials, schema, dependencies, or dataset were reset. Main remains
offline. The release is the tested application commit; subsequent documentation
changes do not change its application files.

## Behavior

`/profile` retains its photo, preferences, history and statistics. Three native
disclosures each contain an independent CSRF-protected form. All volunteer types,
including an unrecorded type, can use them. Account identity comes from the signed
session; submitted IDs, roles and emails never select or modify another account.

| POST | Changes | Validation |
| --- | --- | --- |
| `/profile/name` | `User.name` | Trimmed, 1–100 printable Unicode characters |
| `/profile/campus` | Campus and college in one commit | Official catalogue and matching campus affiliation |
| `/profile/password` | Password hash, auth version, unused reset tokens | Current password, shared configurable policy, confirmation, no reuse |

Successful saves return 303 to the relevant profile section without evaluating
profile analytics. Validation and save failures render 422, expand the failed
section, focus its error summary and preserve non-password inputs. Password inputs
are never refilled. The sixth password attempt in a 15-minute failure window
returns 429. No other profile operation is blocked by this password limit.

Password changes refresh and lock the account, recheck the session version, and
commit the hash, version increment, reset-token invalidation and audit together.
Only after commit is this browser's session version updated. Other sessions fail
the existing version guard on their next request. Failure records use the existing
authentication-event store; a bounded locking read observes concurrent failures
under MySQL repeatable-read isolation. Failed commits roll back without logging
credentials or SQL exception parameters. Successful audit records contain account
IDs and, for campus changes, the old/new campus IDs.

Campus changes immediately affect reports based on the volunteer's current
affiliation. They do not edit registrations, attendance, cancellations, activity
campuses or annual activity mappings. Activity-based campus evidence retains its
host-campus attribution.

## Verification: 2 November 2026

- 30 account-setting cases passed, including all volunteer types, Unicode names,
  malformed campus pairs, field allowlists, access controls, CSRF, session/token
  invalidation, throttling, stale requests and failed-commit rollback.
- The campus-change case checks the existing annual-goal summary before and after
  moving a volunteer; the mapped unique-attendee goal remains achieved.
- Two real MariaDB 10.4.32 concurrency cases passed on a disposable localhost
  schema: two valid changes yield one success and one stale-session rejection;
  simultaneous failures with four previous attempts yield 422 and 429, with
  exactly five recorded failures. The local helper was stopped afterward.
- The broader selected profile, campus, session, form-submit and recovery group
  produced 92 passes, six temporary-directory setup restrictions, two Node
  subprocess restrictions and one existing recovery failure. All eight restricted
  cases passed when rerun with local process access and a fresh workspace temp
  directory: 100 distinct selected cases passed across these runs.
- The remaining recovery case
  `test_temporary_password_requires_new_password_then_becomes_unusable` also
  fails on unchanged `c960159`: it expects `newpassword123` to satisfy a policy
  requiring uppercase and special characters. This feature preserves that policy;
  the complete test suite is not claimed green.
- Isolated Chromium checks passed at 1440, 900, 768, 390 and 320 pixels: keyboard
  disclosures and visible focus, 44px account controls, no horizontal overflow,
  dependent college reset, campus save and section anchor, focused errors, cleared
  passwords, show/hide controls, and cancelled unsaved-change navigation followed
  by a usable retry. Inactive show/hide buttons also stay hidden with JavaScript
  disabled. No JavaScript page errors.

## UI review

Antislop was applied during implementation. Design read: the volunteer's identity
remains the focal point; native disclosures keep occasional account edits separate
from frequent preferences. Existing PSU Inter typography, navy, blue and spacing
are reused. ENERGY 1 / RHYTHM 2 / MOTION 1; no new animation or decorative assets.

Reviewed the changed template, stylesheet, profile script and submit-state script
against the current [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)
fetched on 2 November 2026. No unresolved in-scope findings: semantic controls,
labels, autocomplete, linked inline errors, focus, navigation protection, explicit
native select colors and bounded mobile layout were checked. Existing shared
submit feedback is reused. Contrast checker: blue `#00408b` on white 9.97:1;
error text `#98201c` on white 8.21:1. Desktop and mobile screenshots were inspected.
This is not a full-site accessibility audit; physical devices, screen readers and
Safari/Firefox were not manually tested.

## Live deployment checks: 11 November 2026

The deployed revision and all three POST-only endpoints were verified in the new
container; the profile template compiles. The public login page and profile
JavaScript/CSS returned HTTP 200. Asset hashes match the tested source. Anonymous
profile access requires sign-in. Mail suppression remains enabled.

Aggregate counts before/after: accounts 97/97, registrations 433/433, attendance
296/296, annual targets 30/30 and cancellation requests 24/24. Activity count grew
29/30 during normal use; a successful POST `/create_activity` appears in network
logs at 13:44:41 GMT+8, consistent with that addition. The agent ran no activity
creation or account-update requests. The full-account checksum was rejected by
automatic approval review because it unnecessarily reads personal data/password
hashes; aggregate verification was used instead. No sensitive account rows were
exported. Signed-in live profile editing and password changes remain unexercised;
the local test results above cover those behaviors.

## Reproduce locally

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_settings.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/qa_profile_settings.py
```

The browser check uses an isolated testing app and local credentials. It writes
ignored `.qa-profile-settings-*.png` previews, never accesses Railway, and needs
the already installed Playwright Chromium runtime.

For the optional locking checks, first provision a disposable local MySQL/MariaDB
schema whose name starts with `psu_profile_`; the application creates/seeds its
tables. Use its URL, for example:

```powershell
$env:PROFILE_TEST_DATABASE_URL='mysql+mysqldb://root@127.0.0.1:34071/psu_profile_settings_20261102'
.\.venv\Scripts\python.exe -m pytest tests/test_profile_settings_mysql.py -q -p no:cacheprovider
Remove-Item Env:PROFILE_TEST_DATABASE_URL
```

The test rejects remote hosts and non-dedicated schema names. Each invocation
creates isolated race accounts; do not use a database containing wanted records.
Without the variable, these two optional cases skip. Use the appropriate local
port and credentials; no new dependency or Railway service is required.

For regression checks, run the following with local subprocess access and a fresh
pytest temporary directory if the OS default directory is restricted:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profile_repair.py tests/test_fixed_campuses.py tests/test_form_submit_state.py tests/test_session_idle.py tests/test_password_recovery.py -q -p no:cacheprovider
```

Deployment is a separate step. Rollback of this feature restores the preceding
application code; no schema rollback is needed. User changes made after release
are real account edits and must not be overwritten by an application rollback.
