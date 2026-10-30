# Large demonstration dataset

30 October 2026. Publication authorized to `thesis/main`; hosted deployment and
database execution require separate verification after the push.

## Scope

`reset-and-seed-demo` replaces activities titled `[Demo Analytics] ...` or
`[Demo Dataset] ...`, their registrations, attendance, cancellation requests,
recommendation logs, announcements and event notifications. It also replaces
`DEMO-EXT-...` external participants and its own generated audit entries.
It refuses replacement if a marked external participant has registrations in
unmarked activities. Existing operational audit history and uploaded files stay
untouched; database record removal does not erase files from the upload volume.

All existing login accounts, password hashes and IDs are preserved, including
`student@psu.edu`, `coordinator@psu.edu` and `director@psu.edu`. These three must
already exist with their correct roles. Missing student/coordinator campus links
are repaired using the first existing campus in alphabetical order; valid campus
links are retained. Existing demographics and policy acceptances are unchanged.
An existing volunteer missing a sex response still completes the normal profile
gate after login. No consent is recorded on behalf of preserved accounts.

The new fixture contains:

- 750 participating internal volunteers (the existing student and 749 generated
  identities), across the existing campus catalogue (normally nine campuses).
- A synthetic coordinator for each campus not covered by the preserved
  coordinator. No new administrator or director accounts are generated.
- 200 activities: 165 past and 35 upcoming, spanning roughly 22 months before
  execution and ten weeks after it. There are full, available and zero-capacity
  examples, targets below/at/above verified attendance, missing/partial attendance,
  and optional NDA examples. There is no event-cancelled field in the current
  model, so no fictional event status or new schema field is introduced.
- 5,000 registrations, including 1,000 external registrations; 4,000 attendance
  records; 200 external identities; 150 cancellation requests (50 of each
  decision); 600 SDG mappings; 4,000 in-app notifications; 200 fixture audit rows.
- Pending registrations, completed participation with present/absent/excused
  attendance, and future approved cancellations. No attendance is dated in the
  future. Registrations without attendance include ended activities needing review.

Names, event details and sex responses are synthetic. Sex responses are generated
independently of names. Distribution is illustrative, not calibrated to the
original PDF or an asserted PSU demographic breakdown. Generated emails use the
reserved `.invalid` domain. New accounts have random undisclosed passwords; use
the preserved accounts for the presentation. Repeat runs reuse generated accounts
and preserve their passwords. Unmarked activities and imported historical source
records remain intact, so whole-database totals can exceed fixture counts.

## Railway operation after deployment

This command is available only after the new source reaches the demo app.
Run in the **PSU-Volunteer-Hub-Demo application service console**, at the Linux
shell prompt. If the prompt is `>>>`, enter `exit()` first.

1. Back up the separate demo database. Check the demo application's DATABASE_URL
   reference points to the demo MySQL service, not the main MySQL service.
2. Inspect the target and replacement counts:

   ```bash
   flask --app wsgi:app reset-and-seed-demo --database railway --dry-run
   ```

3. After checking that the displayed database host belongs to the demo database:

   ```bash
   flask --app wsgi:app reset-and-seed-demo --database railway
   ```

4. Type the exact `RESET DEMO <host>/railway` phrase shown by the command. The
   command preserves passwords; it does not restore any previously shared password.
5. Check the reported counts and visit opportunities, both dashboards, analytics
   and the cancellation review workspace using the preserved accounts.

The command checks the approved demo app service ID
`5ba9ae8d-fdd4-4850-a193-dcb5760a6e72`, exact configured database name and three
account roles, then requires typed target confirmation. Service identity alone
cannot prove that DATABASE_URL was configured correctly, hence the separate host
check. The schema must already be complete. No create/drop/alter table, migration,
reference-policy publication, email delivery or deployment occurs in this command.
Replacement and generation share one database transaction and commit once.

## Verification

Isolated SQLite, foreign keys enabled:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_dataset.py tests/test_historical_import.py tests/test_production_init.py -q -p no:cacheprovider
```

Result: **15 passed in 27.58 seconds**. Includes exact fixture counts, cancelled
versus active registration decisions, future full/available events, partial
attendance, chronology, unchanged existing accounts/passwords/unmarked activities,
repeat-run replacement, rollback after injected failure, wrong-service/database/
role/confirmation rejection, no-write preview, external ownership protection,
and HTTP 200 responses for public opportunities, Director dashboard/analytics/CSV
and Coordinator dashboard/analytics. New identity password hashing is stubbed in
the large database-logic test to keep the check fast; application hash verification
remains unchanged. This is not a new full-suite or hosted MySQL verification.

Publication check: the same 15 tests passed in 26.98 seconds against a temporary
checkout of exactly the staged files, excluding the unrelated working-tree edits.

Publication includes only this dataset command, its tests and related documentation.
No live database write or backup was performed. Existing uncommitted
security/recovery changes and attachments remain outside this publication.
