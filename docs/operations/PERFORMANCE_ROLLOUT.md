# Query and concurrency rollout

This change preserves accounts, participation, annual targets, policy records and uploads.
The presentation and existing large seed commands are unchanged. Performance fixture
tools refuse Railway URLs and require a local database named `psu_perf_*`.

## Candidate and runtime

Use the `codex/performance-workflows` branch for Demo. Both Railway apps currently
watch `main`; publishing this branch alone does not deploy either app. Change only
Demo's source branch to the candidate before deploying it. Keep main on its previous
commit until Demo passes the checks below and a 30-minute observation period.

The Docker start command uses one Gunicorn `gthread` worker, four threads and the
existing 120-second timeout. Production SQLAlchemy uses:

| Setting | Value |
|---|---:|
| `pool_pre_ping` | `True` |
| `pool_recycle` | 300 seconds |
| `pool_size` | 5 |
| `max_overflow` | 0 |
| `pool_timeout` | 5 seconds |
| driver `connect_timeout` | 5 seconds |

Request sessions remain scoped by Flask's application/request context. Writes are
never automatically replayed after a lost connection. Capacity changes serialize
on the activity row; attendance updates only the submitted participants, up to 50.

Enable measurements on Demo through Railway Variables:

```dotenv
PERFORMANCE_METRICS_ENABLED=true
PERFORMANCE_SLOW_QUERY_MS=100
MAIL_SUPPRESS_SEND=true
```

Logs contain endpoint, status, elapsed time, SQL count, cumulative SQL time and
hashed slow-statement fingerprints. They omit SQL text, parameters, query strings,
credentials and participant identities. Disable measurements after observation if
the log volume is unnecessary. Changes appear on the next request; there is no
shared cache to invalidate.

## Disposable benchmark

Create an empty local MySQL/MariaDB schema named `psu_perf_20261102_full` with
`utf8mb4`. Supply its URL privately as `PERFORMANCE_TEST_DATABASE_URL`; do not put
real application credentials in scripts or Git. Use `mysql+mysqldb` to match the
production mysqlclient driver. These commands run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_workflows.py --database-url $env:PERFORMANCE_TEST_DATABASE_URL --apply-indexes --hold-seconds 900 --ramp-seconds 60 --output .qa-presentation-temp/performance-50users-15minutes.json
```

The runner creates 1,000 activities, 50,000 registrations, 30 mapped annual goals,
repeat attendees, partial attendance, cancellation states, active policy acceptances, notifications and
historical records. It refuses to replace an existing participation dataset. Use
`--reuse` only for an existing disposable fixture; each run adds local workflow
records. Warmed probes precede 10- and 25-user ramps, then a 50-user hold with
2–5 seconds between actions. Navigation is 70%, filters/evidence 20%, writes 10%.
The final stages combine a 50-request burst with a PDF export and race 20 applicants
for one remaining place. Persisted states and duplicate registrations are checked.

The Windows runner uses Werkzeug with four request slots. This checks concurrent
Flask sessions and database behavior, **not Gunicorn or Railway capacity**. Its
JSON separates ramp, hold, burst and race timings. CPU is process CPU time, including
the local clients; RSS excludes the separate database process. Database connection
sampling adds one connection within the same pool. Provide `--memory-budget-mb`
with the actual app allowance to calculate memory headroom. Missing headroom is
reported as `null`, never a pass. Cold starts require separate hosting measurements.

For an index comparison, use a different fresh local schema:

```powershell
.\.venv\Scripts\python.exe scripts/profile_performance_indexes.py --database-url $env:PERFORMANCE_INDEX_DATABASE_URL --output .qa-presentation-temp/performance-indexes.json
```

This records plain `EXPLAIN` and warmed SELECT timings before/after the additive
indexes, verifies apply/rollback/idempotence, and leaves candidate indexes installed
on that disposable schema. Do not run these tools on application databases.

## Backup and maintenance gate

Before live index changes or an app/volume region move, verify a restorable database
backup and a separate upload-volume backup. Reserve at most 15 minutes of maintenance.
Record the active app commit, source branch, private database host/name, app/database
regions, start-command overrides, variable values and mounted volume paths privately.

Use a MySQL client compatible with the server. From an authorized private shell,
with `DB_HOST`, `DB_USER`, `DB_NAME` and `BACKUP_DIR` already set to the verified
destination and protected backup directory:

```sh
set -eu
umask 077
mysqldump --host="$DB_HOST" --user="$DB_USER" --password \
  --single-transaction --quick --routines --triggers --events --hex-blob \
  --result-file="$BACKUP_DIR/before-performance.sql" "$DB_NAME"
test -s "$BACKUP_DIR/before-performance.sql"
```

Require a successful dump exit status. Restore into a separate empty recovery
database using privately supplied `RESTORE_HOST`, `RESTORE_USER`, `RESTORE_DB`:

```sh
mysql --host="$RESTORE_HOST" --user="$RESTORE_USER" --password \
  "$RESTORE_DB" < "$BACKUP_DIR/before-performance.sql"
```

Check table counts, foreign keys, account access and upload access in that isolated
recovery destination. Store backups encrypted outside the repository and public
upload tree. No live database restore, dataset reset or database-region move belongs
to this performance rollout.

Back up the application volume separately while uploads are paused:

```sh
tar -C /data -czf "$BACKUP_DIR/uploads-before-performance.tar.gz" public private
tar -tzf "$BACKUP_DIR/uploads-before-performance.tar.gz" > "$BACKUP_DIR/uploads-manifest.txt"
```

Test extraction into an explicitly separate empty directory supplied as
`RESTORE_UPLOAD_DIR`, then check representative public and private uploads there:

```sh
tar -C "$RESTORE_UPLOAD_DIR" -xzf "$BACKUP_DIR/uploads-before-performance.tar.gz"
```

## Index preview, apply and rollback

After Demo runs the candidate, open **Demo's application console**, not its MySQL
container. Verify its printed host/database before continuing:

```sh
flask --app wsgi:app migrate-performance-indexes --database railway --dry-run
```

Inspect actual existing indexes and representative `EXPLAIN` plans. The migration
skips equivalent left-prefix coverage and rejects mismatched names/columns. No DDL
runs at application startup. The eight candidates cover activity date/campus lists,
registration capacity/history, attendance, notification order/unread and auth throttling.
Only apply candidates supported by measured plans; equivalent definitions are skipped.
Keep writers paused for the maintenance operation, then run:

```sh
flask --app wsgi:app migrate-performance-indexes --database railway
```

Type `ADD PERFORMANCE INDEXES railway` at the prompt after verifying backup and
destination. MySQL DDL commits independently; a failure can leave earlier indexes
installed. Inspect with dry-run before deciding what remains. The session uses a
five-second metadata/row lock wait. Do not increase timeouts to hide a blocked migration.

Rollback is optional; normally leave harmless additive indexes when reverting code:

```sh
flask --app wsgi:app migrate-performance-indexes --database railway --rollback --dry-run
flask --app wsgi:app migrate-performance-indexes --database railway --rollback
```

Type `REMOVE PERFORMANCE INDEXES railway` only for a reviewed rollback. MySQL may
silently remove an old automatic foreign-key index when a composite index replaces
it. Rollback first creates missing `ix_fk_*` support indexes, then drops only owned
`ix_perf_*` indexes. It preserves all constraints and unrelated indexes.

## Regions, validation and release

For deployed Gunicorn checks without replacing presentation records, upload
`scripts/probe_deployed_demo.py` to `/app/probe_deployed_demo.py` through Demo's
Console Files drawer, then run from `/app`:

```sh
python probe_deployed_demo.py --users 1 --seconds 10 --output /data/operations-backup-20261102/demo-smoke.json
python probe_deployed_demo.py --users 10 --seconds 60 --output /data/operations-backup-20261102/demo-10.json
python probe_deployed_demo.py --users 25 --seconds 60 --output /data/operations-backup-20261102/demo-25.json
python probe_deployed_demo.py --users 50 --seconds 900 --output /data/operations-backup-20261102/demo-50.json
```

This utility rejects any service/database except the approved Demo. It uses
existing accounts and temporary signed sessions held in process memory; it does
not check passwords or print session cookies. GET requests pass through the actual
Gunicorn listener. Ordinary GET side effects, such as recommendation logs, remain.
It does not submit participation changes. Its timings include app/database work
and exclude the public edge and the user's network. Record these limitations:
this run uses the current presentation dataset, while the separate disposable
50,000-registration workload covers the mixed writes and large-data case.

Recheck actual regions and private URLs in Railway. Demo was observed in Southeast
Asia and its database in US East before this rollout; this is an avoidable network
round trip for every query. Keep the database stationary. Move the app and its
upload volume to the existing database region only with a verified volume restore
and a procedure that fits the maintenance window. Otherwise defer the move and
record its effect. Do not create services, increase paid capacity or expose private
database access to obtain benchmark results.

Confirm default Admin, Student, Coordinator and Director access on Demo. Check page
filters and pagination on desktop/mobile; registration/cancellation reviews;
attendance page boundaries and certificate eligibility; campus/university annual
goals including pending evidence; rankings; and complete CSV/PDF exports. Confirm
email is suppressed. Compare warmed p95 and SQL counts against the approved targets;
capture CPU, peak memory, connections and cold-start behavior separately. No worker
timeout, unexplained 500, connection exhaustion, duplicate signup or lost update is
acceptable. Require 20% memory headroom using the actual service allowance.

After Demo passes and remains healthy for 30 minutes, release the **same commit**
to `thesis/main`, apply the same reviewed migration on main during its maintenance
window, and repeat default-account smoke checks. Never push the candidate to main
to trigger Demo validation, because both services originally watched that branch.

If validation fails, return Demo to its recorded prior app commit/start command and
variables. Revert an app/volume move only through the verified volume procedure.
Keep main unchanged and report the measured limit. Do not reset data as rollback.

References: [SQLAlchemy pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html),
[MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html),
[Gunicorn 22 threads](https://raw.githubusercontent.com/benoitc/gunicorn/22.0.0/docs/source/design.rst),
[Railway private networking](https://docs.railway.com/networking/private-networking/how-it-works).
