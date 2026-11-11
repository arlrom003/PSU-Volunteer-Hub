"""Compare EXPLAIN and warmed SELECT timings on a fresh local benchmark only."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--reuse', action='store_true', help='Reuse an existing disposable fixture without candidate indexes')
    args = parser.parse_args()
    from sqlalchemy.engine import make_url
    url = make_url(args.database_url)
    if (url.get_backend_name() not in ('mysql', 'mariadb') or
            url.host not in ('127.0.0.1', 'localhost') or not (url.database or '').startswith('psu_perf_')):
        parser.error('Only a disposable local MySQL/MariaDB psu_perf_* database is allowed.')
    from config import TestingConfig
    TestingConfig.SQLALCHEMY_DATABASE_URI = args.database_url
    from app import create_app
    from app.models import db
    from app.models.event import Event
    from app.models.user import AuthSecurityEvent, User
    from app.performance_indexes import migrate_indexes, INDEXES
    from sqlalchemy import inspect, insert, text
    from tests.performance_fixture import build_performance_fixture
    app = create_app('testing')
    with app.app_context():
        if any(index['name'].startswith('ix_perf_') for table in INDEXES
               for index in inspect(db.engine).get_indexes(table)):
            parser.error('Use a fresh disposable schema without the candidate indexes.')
        if not args.reuse:
            build_performance_fixture(app)
        now = datetime.now()
        if not AuthSecurityEvent.query.count():
            db.session.execute(insert(AuthSecurityEvent), [dict(action='login' if i % 2 else 'reset',
                subject_hash=AuthSecurityEvent.subject(str(i % 1000)),
                created_at=now-timedelta(minutes=i % 60)) for i in range(20000)])
        db.session.commit()
        person = User.query.filter_by(email='benchmark-0@example.test').one()
        params = dict(now=now, cutoff=now-timedelta(minutes=30), user=person.id,
                      campus=person.campus_id, event=Event.query.first().id,
                      subject=AuthSecurityEvent.subject('5'))
        db.session.remove()
        queries = dict(
            activities='SELECT id, date FROM events WHERE date >= :now ORDER BY date, id LIMIT 9',
            campus_activities='SELECT id, date FROM events WHERE campus_id=:campus AND date >= :now ORDER BY date, id LIMIT 25',
            capacity="SELECT count(*) FROM registrations WHERE event_id=:event AND status IN ('confirmed','completed')",
            history='SELECT id FROM registrations WHERE user_id=:user ORDER BY registered_at DESC, id DESC LIMIT 25',
            attendance="SELECT user_id, count(*) FROM attendance WHERE event_id=:event AND status='present' GROUP BY user_id",
            notifications='SELECT id FROM notifications WHERE user_id=:user ORDER BY created_at DESC, id DESC LIMIT 25',
            unread='SELECT count(*) FROM notifications WHERE user_id=:user AND is_read=0',
            throttle="SELECT count(*) FROM auth_security_events WHERE action='login' AND subject_hash=:subject AND created_at >= :cutoff")
        def measure():
            result = {}
            with db.engine.connect() as connection:
                for name, sql in queries.items():
                    plan = [dict(row) for row in connection.execute(text('EXPLAIN '+sql), params).mappings()]
                    times = []
                    for _ in range(7):
                        start = perf_counter()
                        connection.execute(text(sql), params).all()
                        times.append((perf_counter()-start)*1000)
                    result[name] = dict(median_ms=round(median(times[1:]), 3), explain=plan)
            return result
        before = measure()
        migration = migrate_indexes(db.engine, url.database, dry_run=False)
        after = measure()
        with db.engine.connect() as connection:
            version = connection.execute(text('SELECT VERSION()')).scalar()
        result = dict(database=url.get_backend_name(), server=version,
                      migration=migration, before=before, after=after)
        assert migrate_indexes(db.engine, url.database) == []
        migrate_indexes(db.engine, url.database, dry_run=False, rollback=True)
        assert len(migrate_indexes(db.engine, url.database)) == len(migration)
        migrate_indexes(db.engine, url.database, dry_run=False)
        result['idempotence_and_rollback'] = 'passed'
        Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({name: dict(before=before[name]['median_ms'], after=after[name]['median_ms'],
            old_key=[row['key'] for row in before[name]['explain']],
            new_key=[row['key'] for row in after[name]['explain']]) for name in queries}, indent=2))


if __name__ == '__main__':
    main()
