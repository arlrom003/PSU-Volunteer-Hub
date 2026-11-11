"""Exercise Demo's actual Gunicorn with GET requests; never replace its dataset."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import sys
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users', type=int, choices=(1, 10, 25, 50), default=1)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if os.getenv('RAILWAY_SERVICE_ID') != '5ba9ae8d-fdd4-4850-a193-dcb5760a6e72':
        parser.error('Run only in the approved Demo application container.')
    if not 10 <= args.seconds <= 900:
        parser.error('Duration must be between 10 and 900 seconds.')
    sys.path.insert(0, str(Path.cwd()))
    from wsgi import app
    from app.models import db
    from app.models.event import Event
    from app.models.user import User
    from datetime import datetime
    with app.app_context():
        if db.engine.url.host != 'mysql-tgn.railway.internal' or db.engine.url.database != 'railway':
            parser.error('The configured database is not the approved Demo destination.')
        if not app.config.get('MAIL_SUPPRESS_SEND'):
            parser.error('Demo email suppression must be enabled.')
        serializer = app.session_interface.get_signing_serializer(app)
        people = User.query.filter_by(_is_active=True).order_by(User.id).all()
        defaults = {u.role: u for u in people if u.email in (
            'admin@psu.edu', 'director@psu.edu', 'coordinator@psu.edu', 'student@psu.edu')}
        if set(defaults) != {'admin', 'director', 'coordinator', 'volunteer'}:
            parser.error('The four preserved default accounts are required.')
        ended = Event.query.filter(Event.campus_id == defaults['coordinator'].campus_id,
            Event.end_date < datetime.now()).order_by(Event.id).first()
        attendance_path = f'/attendance?event_id={ended.id}' if ended else '/attendance'
        routes = {
            'admin': ['/admin_dash?tab=users', '/notifications'],
            'director': ['/director_dash', '/analytics?period=all', '/annual-goals?year=2026', '/notifications'],
            'coordinator': ['/coordinator_dash?period=all&status=all', attendance_path,
                '/coordinator/cancellation-requests', '/coordinator_analytics?period=all'],
            'volunteer': ['/volunteer_dash', '/volunteer_dash?page=2', '/opportunities', '/notifications'],
        }
        def actor(person):
            cookie = app.config['SESSION_COOKIE_NAME'] + '=' + serializer.dumps(dict(
                _user_id=str(person.id), _fresh=True, auth_version=person.auth_version))
            return person.role, cookie, routes[person.role]
        default_actors = [actor(defaults[role]) for role in ('admin', 'director', 'coordinator', 'volunteer')]
        volunteers = [actor(u) for u in people if u.role == 'volunteer' and u.sex]
        actors = (default_actors[:3] + volunteers)[:args.users]
        if len(actors) < args.users:
            parser.error('There are too few existing active accounts for this concurrency.')
        db.session.remove()
    origin = 'http://127.0.0.1:' + os.getenv('PORT', '8080')
    host = 'psu-volunteer-hub-demo-production.up.railway.app'
    def fetch(actor, path):
        role, cookie, _ = actor
        started = monotonic()
        request = Request(origin + path, headers={'Cookie': cookie, 'Host': host})
        try:
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                response.read()
                status = response.status
        except HTTPError as exc:
            status = exc.code
            exc.close()
        except OSError:
            status = 0
        return dict(role=role, path=path, status=status, ms=round((monotonic()-started)*1000, 2))
    probes = [fetch(actor, path) for actor in default_actors for path in actor[2]]
    deadline = monotonic() + args.seconds
    def browse(index):
        actor = actors[index]
        rng = random.Random(index)
        samples = []
        while monotonic() < deadline:
            samples.append(fetch(actor, rng.choice(actor[2])))
            sleep(rng.uniform(2, 5))
        return samples
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        samples = [sample for group in pool.map(browse, range(args.users)) for sample in group]
    groups = {}
    for sample in samples:
        groups.setdefault(sample['path'], []).append(sample['ms'])
    result = dict(scope='Demo loopback HTTP through deployed Gunicorn; existing presentation dataset; GET only',
        users=args.users, seconds=args.seconds, revision=os.getenv('RAILWAY_GIT_COMMIT_SHA'),
        probes=probes, requests=len(samples), errors=[s for s in probes+samples if s['status'] != 200],
        latency={path: dict(count=len(values), p95_ms=sorted(values)[int((len(values)-1)*0.95)],
            max_ms=max(values)) for path, values in groups.items()})
    os.umask(0o077)
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
