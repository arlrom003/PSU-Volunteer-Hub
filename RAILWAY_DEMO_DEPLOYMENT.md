# Railway thesis demonstration deployment

Local preparation only. No cloud project, billable upgrade, deployment or database
upload has been performed. Preserve the local original database and backup files.

## Check the account before creating services

Confirm actual remaining trial credit, expiry, available memory and volume count.
This layout needs two persistent volumes: one for MySQL and one for the app's
uploads. Railway documents 3 volumes for Trial versus 1 for ongoing Free. Do not
assume this layout stays free after trial expiry or that credits cover defense
day. Stop for user approval if trial limits cannot accommodate it; no paid upgrade.

Use a new project such as `psu-volunteer-thesis-demo`, not an existing production
project. Synthetic demonstration records only. Do not upload local SQL exports,
backup folders, real accounts, .env files, credentials, or Git history as an image.
The current Dockerfile's explicit COPY/context allowlists exclude these and
existing uploaded files; local PSU assets and shared styles remain included.

## Services and settings

1. Add a new private MySQL service and its persistent database volume. Keep public
   database networking off. Choose a region available in the account near the
   audience, and put both services in the same region/project.
2. Add the app from the approved source revision. Railway should detect the root
   Dockerfile. Do not use `app:app` or `flask run`. Docker CMD starts `wsgi:app`
   with one Gunicorn worker, binds Railway's PORT, and never seeds/initializes DB.
3. Attach an app volume at **/data**. The image maps `/app/static/uploads` to
   `/data/public`; private milestones use `/data/private`. Only uploads are on
   the volume, not all static assets. Verify that the volume is actually attached;
   creating /data inside ephemeral disk alone does not provide persistence.
4. Set app variables privately:

   | Variable | Value/source |
   | --- | --- |
   | APP_ENV | production (also image default) |
   | SECRET_KEY | Newly generated strong secret, not the local development secret |
   | DATABASE_URL | Reference the new MySQL service's private MYSQL_URL; never local/source DB |
   | PRIVATE_UPLOAD_FOLDER | /data/private (image default) |
   | TRUSTED_PROXY_COUNT | Confirm Railway's actual trusted proxy chain; do not guess extra hops |

   The supplied requirements include mysqlclient for `mysql://` URLs and PyMySQL
   for `mysql+pymysql://`. Verify the actual private URL format without printing
   credentials. Do not use the public database URL for the app's internal link.
   For reset emails, set `MAIL_PROVIDER=brevo`, `BREVO_API_KEY` privately,
   `MAIL_DEFAULT_SENDER` to your verified Brevo sender, and
   `MAIL_SUPPRESS_SEND=false`. Free, Trial, and Hobby plans require HTTPS email
   APIs because Railway blocks outbound SMTP. See the Brevo setup in `README.md`.
   Live inbox delivery must still be verified after deployment.
5. Set healthcheck path **/auth/login**, timeout **120 seconds**, restart policy
   **On Failure**, maximum retries **3**, and one app replica in dashboard settings.
   The healthcheck proves HTTP liveness only, not initialized schema or DB health.
   Railway's legacy railway.json/toml Config as Code is deprecated, so no new
   legacy configuration file is introduced; Dockerfile plus dashboard settings
   are used for this small demo.

## Initialize and populate deliberately

While not yet public, run in the deployed app's environment via an approved
interactive shell, checking the exact new database name:

```sh
flask --app wsgi:app init-production --database EXACT_NEW_MYSQL_DATABASE_NAME
```

The user enters and confirms the first Admin password privately. Do not place
passwords in deployment variables solely for seeding, shell arguments or logs.
Do not run setup in build/pre-deploy/CMD; it is a one-time empty-target operation.
It refuses existing tables/views. If schema already exists, investigate the demo
target without dropping it or touching the original database.

Use Admin workflows to create synthetic coordinator, director and volunteer
accounts with unique temporary passwords. Configure demo policies explicitly;
user must review any actual Terms acceptance. Add synthetic past/active/future
activities and attendance through existing workflows; optional `seed-demo-analytics`
is only an explicit operator action on this verified new demonstration database,
after suitable volunteer users exist. Never use development auto-seeding on cloud.

## Before sharing the link

Generate a Railway HTTPS domain only after data/configuration review. Verify:

- HTTPS redirects, secure cookies, correct proxy-derived scheme and no debug mode.
- All four role sign-ins and authorization boundaries, campus scoping, logout.
- Consent, joining, cancellation Approve/Reject, early check-in/final attendance.
- Profile/event uploads and authorized private milestone download. Redeploy and
  confirm both database data and public/private uploads persist.
- Descriptive analytics/PDF/CSV, cosine recommendations, desktop/mobile navigation.
- Actual memory/build/storage usage versus remaining credits; heavy scientific
  dependencies may exceed small trial limits. Do not promise a free deployment
  until the actual build and resource use have been measured.

Use synthetic data, disable real outbound messaging unless explicitly configured,
and keep the working local demo available as a defense-day fallback. Remove demo
access after the demonstration using an approved retention/cleanup decision.

## Verification so far

- 20 focused deployment-file/startup/provisioning tests passed initially.
- 21 October follow-up: Linux Docker image built successfully; real Gunicorn
  startup and public/private upload plus synthetic SQLite data persistence across
  replacement containers passed with no network access. 18 startup/provisioning
  checks passed in the Linux image environment. See DOCKER_DEMO_QA.md for exact
  coverage, retained artifacts and limits. Actual Railway deployment, proxy chain,
  cloud MySQL connection and mounted-volume behavior remain unverified.
- No application/UI changes, new Python dependencies, commit/push, paid upgrade
  or actual cloud writes. Pending backup/runbook documents are preserved.

References: [Flask deployment](https://docs.railway.com/guides/flask),
[MySQL](https://docs.railway.com/databases/mysql),
[Volumes](https://docs.railway.com/volumes/reference),
[Config as Code deprecation](https://docs.railway.com/config-as-code/reference).
