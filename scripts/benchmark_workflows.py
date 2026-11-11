"""Run local-only request probes and a mixed workload against a disposable database."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib.util
import json
import logging
import os
from pathlib import Path
import random
import re
import sys
from threading import Event as ThreadEvent, Lock, Semaphore, Thread
from time import perf_counter, process_time, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def percentile(values, percent):
    return sorted(values)[min(len(values)-1, int((len(values)-1)*percent/100))] if values else None


def acceptance(result):
    limits = {'/opportunities': 1000, '/notifications': 1000, '/volunteer_dash': 2000,
              '/coordinator_dash': 2000, '/attendance': 2000, '/annual-goals': 2000,
              '/director_dash': 3000, '/analytics': 3000,
              '/coordinator/cancellation-requests': 2000, '/opportunities/register/:id': 2000,
              '/registrations/:id/cancel': 2000, '/reports/university.pdf': 10000}
    ceilings = {'events.volunteer_dash:GET': 20, 'coordinator.coordinator_dash:GET': 20,
                'coordinator.analytics:GET': 20, 'coordinator.attendance:GET': 20,
                'director.director_dash:GET': 25, 'director.analytics:GET': 25,
                'goals.details:GET': 20, 'notifications.list_notifications:GET': 8,
                'events.register_for_event:POST': 15, 'events.cancel_registration:POST': 15,
                'coordinator.cancellation_requests:POST': 15, 'coordinator.attendance:POST': 15}
    latency = [key for key, value in result['latency'].items()
               if key.split(':', 1)[0] in ('50_users', 'burst_and_export')
               and value['p95_ms'] > limits[key.split(':', 1)[1]]]
    queries = [key for key, count in result['query_maxima'].items()
               if key in ceilings and count > ceilings[key]]
    probe_limits = {'/opportunities': 7, '/volunteer_dash': 20, '/coordinator_dash': 20,
        '/coordinator_analytics': 20, '/attendance': 20, '/director_dash': 25, '/analytics': 25,
        '/annual-goals': 20, '/notifications': 8}
    for probe in result['probes']:
        path = probe['path'].split('?')[0]
        if path in probe_limits and probe['queries'] > probe_limits[path]:
            queries.append('probe:' + probe['path'])
    public = next(probe for probe in result['probes'] if probe['path'] == '/opportunities')
    if public['queries'] > 7:
        queries.append('public opportunities')
    headroom = result['resources']['memory_headroom_percent']
    return dict(scope='Local four-slot workload; Railway acceptance remains separate',
        latency_failures=latency, query_failures=queries,
        memory_headroom_measured=headroom is not None,
        passed=not (latency or queries or result['errors'] or result['consistency_errors']
                    or headroom is None or headroom < 20))


def resident_bytes():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('peak', 'working', 'peak_paged', 'paged',
                    'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = wintypes.HANDLE
        memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        memory_info.restype = wintypes.BOOL
        if not memory_info(current_process(), ctypes.byref(value), value.cb):
            raise ctypes.WinError()
        return value.working
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True, help='Local psu_perf_* database only; never Railway')
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--probe-only', action='store_true')
    parser.add_argument('--apply-indexes', action='store_true', help='Apply candidate indexes to this local disposable fixture')
    parser.add_argument('--hold-seconds', type=int, default=900)
    parser.add_argument('--ramp-seconds', type=int, default=60)
    parser.add_argument('--output', required=True)
    parser.add_argument('--memory-budget-mb', type=int, help='Existing app memory allowance, for the 20%% headroom check')
    parser.add_argument('--source-root', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    sys.path.insert(0, args.source_root)
    from sqlalchemy.engine import make_url
    url = make_url(args.database_url)
    if url.host not in (None, '', 'localhost', '127.0.0.1') or not Path(url.database or '').name.startswith('psu_perf_'):
        parser.error('Only a named disposable local psu_perf_* database is allowed.')
    from config import TestingConfig
    TestingConfig.SQLALCHEMY_DATABASE_URI = args.database_url
    if url.get_backend_name() in ('mysql', 'mariadb'):
        TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = dict(pool_size=5, max_overflow=0, pool_timeout=5,
            pool_pre_ping=True, pool_recycle=300, connect_args={'connect_timeout': 5})
    from app import create_app
    from app.models import db
    from app.models.user import User
    from app.models.event import Event, Registration, Attendance, CancellationRequest
    from tests.test_system_performance import signed_in_client, query_count
    from werkzeug.serving import make_server
    from flask import g
    app = create_app('testing')
    app.config.update(PERFORMANCE_METRICS_ENABLED=True, PERFORMANCE_SLOW_QUERY_MS=100)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.logger.setLevel(logging.WARNING)
    with app.app_context():
        if not args.reuse:
            source = Path(__file__).resolve().parents[1] / 'tests' / 'performance_fixture.py'
            spec = importlib.util.spec_from_file_location('benchmark_fixture', source)
            fixture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture)
            fixture.build_performance_fixture(app)
        User.query.filter_by(email='student@psu.edu').one().sex = 'female'
        db.session.commit()
        index_changes = []
        if args.apply_indexes:
            from app.performance_indexes import migrate_indexes
            db.session.remove()
            index_changes = migrate_indexes(db.engine, url.database, dry_run=False)
        counts = dict(activities=Event.query.count(), registrations=Registration.query.count())
        if counts['activities'] != 1000 or counts['registrations'] < 50000:
            parser.error('The disposable benchmark must contain 1,000 activities and at least 50,000 registrations.')
        people = User.query.filter(User.email.like('benchmark-%@example.test')).order_by(User.id).limit(50).all()
        coordinator = User.query.filter_by(email='coordinator@psu.edu').one()
        director = User.query.filter_by(email='director@psu.edu').one()
        upcoming = Event.query.filter(Event.date > datetime.now(), Event.campus_id == coordinator.campus_id).order_by(Event.id).all()
        ended = Event.query.filter(Event.end_date < datetime.now(), Event.campus_id == coordinator.campus_id).first()
        attendance_ids = [row[0] for row in db.session.query(Registration.id).filter_by(event_id=ended.id).order_by(Registration.id).limit(50).all()]
        serializer = app.session_interface.get_signing_serializer(app)
        def cookie(person):
            return app.config['SESSION_COOKIE_NAME'] + '=' + serializer.dumps(dict(
                _user_id=str(person.id), _fresh=True, auth_version=person.auth_version))
        director_cookie, coordinator_cookie = cookie(director), cookie(coordinator)
        actors = []
        for i, person in enumerate(people):
            used = {row[0] for row in db.session.query(Registration.event_id).filter_by(user_id=person.id)}
            choices = [event for event in upcoming if event.id not in used]
            if not choices:
                parser.error('Each actor needs an upcoming activity without an existing registration.')
            actors.append(dict(id=person.id, cookie=cookie(person), event=choices[i % len(choices)].id,
                               attendance=attendance_ids[i], phase=0))
        attendance_event = ended.id
    samples, sql_samples, lock = [], [], Lock()
    consistency_errors, resources = [], []
    stop_resources = ThreadEvent()
    def measure_resources():
        while not stop_resources.is_set():
            sample = dict(rss_bytes=resident_bytes())
            if url.get_backend_name() in ('mysql', 'mariadb'):
                with app.app_context(), db.engine.connect() as connection:
                    for name, value in connection.exec_driver_sql(
                            "SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected', 'Threads_running')"):
                        sample[name] = int(value)
            resources.append(sample)
            stop_resources.wait(1)
    @app.after_request
    def capture_sql(response):
        measurement = getattr(g, '_request_measurement', None)
        if measurement:
            with lock:
                from flask import request
                sql_samples.append(dict(endpoint=request.endpoint, method=request.method,
                    queries=measurement['queries'], sql_ms=measurement['sql_ms']))
        return response
    probes = []
    routes = [(None, '/opportunities'), ('volunteer', '/volunteer_dash'),
        ('coordinator', '/coordinator_dash'), ('coordinator', '/coordinator_analytics'),
        ('coordinator', f'/attendance?event_id={attendance_event}'),
        ('director', '/director_dash'), ('director', '/analytics?period=all'),
        ('director', '/analytics?view=historical'), ('director', '/annual-goals'),
        ('director', '/notifications'), ('director', '/reports/university.csv'),
        ('director', '/reports/university.pdf')]
    for role, path in routes:
        client = signed_in_client(app, role)
        warm = client.get(path)
        if warm.status_code != 200:
            parser.error(f'Warm-up failed for {path}: HTTP {warm.status_code}')
        start = perf_counter()
        with query_count(app) as statements:
            response = client.get(path)
        probes.append(dict(role=role, path=path, status=response.status_code, queries=len(statements),
                           elapsed_ms=round((perf_counter()-start)*1000, 2), bytes=len(response.data)))
    result = dict(database=url.get_backend_name(), driver=url.drivername, fixture=counts, probes=probes,
                  index_changes=index_changes, recorded_at=datetime.now().astimezone().isoformat())
    slots = Semaphore(4)
    original_app = app.wsgi_app
    def limited_app(environ, start_response):
        with slots:
            return original_app(environ, start_response)
    app.wsgi_app = limited_app
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monitor = Thread(target=measure_resources, daemon=True)
    monitor.start()
    base = f'http://127.0.0.1:{server.server_port}'
    cpu_start, wall_start = process_time(), perf_counter()
    stage = 'probes'
    def send(path, session_cookie, data=None):
        start = perf_counter()
        request = Request(base+path, headers={'Cookie': session_cookie},
                          data=urlencode(data).encode() if data is not None else None)
        try:
            with build_opener(NoRedirect).open(request, timeout=30) as response:
                response.read()
                status = response.status
        except HTTPError as exc:
            status = exc.code
            exc.read()
        except Exception as exc:
            status = type(exc).__name__
        with lock:
            route = re.sub(r'/\d+(?=/|$)', '/:id', path.split('?')[0])
            samples.append(dict(path=route, stage=stage, write=data is not None, status=status,
                                elapsed_ms=(perf_counter()-start)*1000))
        return status
    def run_actor(index, stop):
        actor = actors[index]
        rng = random.Random(20261101+index)
        while perf_counter() < stop:
            roll = rng.random()
            if roll < .7:
                path, session_cookie = (('/director_dash', director_cookie) if index % 10 == 0 else
                    ('/coordinator_dash', coordinator_cookie) if index % 10 == 1 else
                    ('/volunteer_dash', actor['cookie']))
                if index % 10 not in (0, 1):
                    navigation = rng.randrange(10)
                    if navigation < 2:
                        path = '/opportunities'
                    elif navigation == 2:
                        path = '/notifications'
                send(path, session_cookie)
            elif roll < .9:
                path, session_cookie = (('/annual-goals', director_cookie) if index % 3 == 0 else
                    ('/analytics?period=all', director_cookie) if index % 3 == 1 else
                    ('/opportunities?category=Environment', actor['cookie']))
                send(path, session_cookie)
            else:
                succeeded = False
                if actor['phase'] == 0:
                    send(f'/opportunities/register/{actor["event"]}', actor['cookie'], dict(accept_agreement='yes'))
                    with app.app_context():
                        succeeded = Registration.query.filter_by(user_id=actor['id'], event_id=actor['event'],
                                                                 status='confirmed').count() == 1
                elif actor['phase'] == 1:
                    with app.app_context():
                        registration = Registration.query.filter_by(user_id=actor['id'], event_id=actor['event']).first()
                        registration_id = registration.id if registration else None
                    if registration_id:
                        send(f'/registrations/{registration_id}/cancel', actor['cookie'], dict(reason='Academic Conflict'))
                        with app.app_context():
                            succeeded = CancellationRequest.query.filter_by(registration_id=registration_id,
                                                                             status='pending').count() == 1
                elif actor['phase'] == 2:
                    with app.app_context():
                        cancellation = CancellationRequest.query.join(Registration).filter(
                            Registration.user_id == actor['id'], Registration.event_id == actor['event']).first()
                        cancellation_id = cancellation.id if cancellation else None
                    if cancellation_id:
                        send('/coordinator/cancellation-requests', coordinator_cookie,
                             dict(request_id=cancellation_id, decision='approved', review_note='Benchmark review'))
                        with app.app_context():
                            succeeded = (db.session.get(CancellationRequest, cancellation_id).status == 'approved'
                                and Registration.query.filter_by(user_id=actor['id'], event_id=actor['event'],
                                                                 status='cancelled').count() == 1)
                else:
                    selected_status = rng.choice(['present', 'absent', 'excused'])
                    send('/attendance', coordinator_cookie, dict(event_id=attendance_event,
                         registration_id=actor['attendance'], status=selected_status))
                    with app.app_context():
                        attendance = Attendance.query.filter_by(registration_id=actor['attendance']).one()
                        registration = db.session.get(Registration, actor['attendance'])
                        succeeded = (attendance.status == selected_status and
                            registration.status == ('completed' if selected_status == 'present' else 'confirmed'))
                if succeeded:
                    actor['phase'] += 1
                else:
                    with lock:
                        consistency_errors.append(dict(actor=index, phase=actor['phase']))
            sleep(rng.uniform(2, 5))
    try:
        if not args.probe_only:
            for users, duration in ((10, args.ramp_seconds), (25, args.ramp_seconds), (50, args.hold_seconds)):
                stage = f'{users}_users'
                print(f'Starting {stage} for {duration} seconds', flush=True)
                stop = perf_counter()+duration
                with ThreadPoolExecutor(max_workers=users) as pool:
                    futures = [pool.submit(run_actor, i, stop) for i in range(users)]
                    for future in futures:
                        future.result()
            stage = 'burst_and_export'
            with ThreadPoolExecutor(max_workers=51) as pool:
                futures = [pool.submit(send, '/opportunities', actor['cookie']) for actor in actors]
                futures.append(pool.submit(send, '/reports/university.pdf', director_cookie))
                for future in futures:
                    future.result()
            stage = 'last_slot_race'
            with app.app_context():
                target = db.session.get(Event, upcoming[-1].id)
                target_id, original_slots = target.id, target.slots
                active_before = Registration.query.filter(Registration.event_id == target_id,
                    Registration.status.in_(('confirmed', 'completed'))).count()
                eligible = [actor for actor in actors if not Registration.query.filter_by(
                    user_id=actor['id'], event_id=target_id).count()][:20]
                assert len(eligible) >= 2
                target.slots = active_before + 1
                db.session.commit()
            with ThreadPoolExecutor(max_workers=20) as pool:
                futures = [pool.submit(send, f'/opportunities/register/{target_id}', actor['cookie'],
                    dict(accept_agreement='yes')) for actor in eligible]
                for future in futures:
                    future.result()
            with app.app_context():
                active_after = Registration.query.filter(Registration.event_id == target_id,
                    Registration.status.in_(('confirmed', 'completed'))).count()
                db.session.get(Event, target_id).slots = original_slots
                db.session.commit()
                result['last_slot_race'] = dict(contenders=len(eligible), accepted=active_after-active_before)
                if active_after != active_before + 1:
                    consistency_errors.append(dict(stage='last_slot_race', expected=1, actual=active_after-active_before))
        groups = defaultdict(list)
        for sample in samples:
            groups[sample['stage'] + ':' + sample['path']].append(sample['elapsed_ms'])
        elapsed = perf_counter()-wall_start
        result.update(runtime='Local Werkzeug with four request slots; not a Gunicorn/Railway measurement',
            duration_seconds=round(elapsed, 2), cpu_seconds=round(process_time()-cpu_start, 2),
            throughput=len(samples)/elapsed, requests=len(samples), writes=sum(s['write'] for s in samples),
            errors=[s for s in samples if s['status'] not in (200, 302)],
            latency={path: dict(count=len(values), p50_ms=percentile(values,50), p95_ms=percentile(values,95),
                               p99_ms=percentile(values,99)) for path, values in groups.items()},
            sql=dict(requests=len(sql_samples), max_queries=max((s['queries'] for s in sql_samples), default=0),
                     p95_ms=percentile([s['sql_ms'] for s in sql_samples],95)))
        stop_resources.set()
        monitor.join(timeout=6)
        peak = max((sample['rss_bytes'] for sample in resources), default=0)
        result.update(consistency_errors=consistency_errors,
            actors_finishing_registration_cancellation=sum(actor['phase'] >= 3 for actor in actors),
            resources=dict(peak_rss_mb=round(peak/1024**2, 2),
                memory_headroom_percent=round((1-peak/(args.memory_budget_mb*1024**2))*100, 1)
                    if args.memory_budget_mb else None,
                max_database_connections=max((sample.get('Threads_connected', 0) for sample in resources), default=0),
                max_database_running=max((sample.get('Threads_running', 0) for sample in resources), default=0)),
            query_maxima={f'{endpoint}:{method}': max(sample['queries'] for sample in sql_samples
                if sample['endpoint'] == endpoint and sample['method'] == method)
                for endpoint, method in {(sample['endpoint'], sample['method']) for sample in sql_samples}})
        with app.app_context():
            duplicate = db.session.query(Registration.user_id, Registration.event_id).group_by(
                Registration.user_id, Registration.event_id).having(db.func.count(Registration.id)>1).first()
            assert duplicate is None
            result['final_registrations'] = Registration.query.count()
        result['acceptance'] = acceptance(result)
        Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
        return 0 if result['acceptance']['passed'] else 1
    finally:
        stop_resources.set()
        monitor.join(timeout=6)
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
