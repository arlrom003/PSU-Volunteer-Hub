"""Query budgets include real annual goals and large participation histories."""
import logging
from datetime import datetime, timedelta
import pytest
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import inspect, event as sqlalchemy_event

from app import create_app
from app.models import db
from app.models.user import User
from app.models.event import Event, Registration, Attendance, CancellationRequest
from app.models.notification import Notification
from app.models.annual_plan import AnnualTarget
from app.performance_indexes import migrate_indexes, INDEXES, index_name
from app.reports import build_events_report, batched_events_report
from tests.performance_fixture import build_performance_fixture
from tests.test_system_performance import query_count, signed_in_client
from tests.html_helpers import parse_html


@pytest.fixture(scope='module')
def benchmark_app():
    instance = create_app('testing')
    with instance.app_context():
        counts = build_performance_fixture(instance)
        assert counts['activities'] == 1000 and counts['registrations'] == 50000
        User.query.filter_by(email='student@psu.edu').one().sex = 'female'
        db.session.commit()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize('role,path,budget', [
    (None, '/opportunities', 7), ('volunteer', '/opportunities', 7), ('volunteer', '/volunteer_dash', 20),
    ('coordinator', '/coordinator_dash', 20), ('coordinator', '/coordinator_analytics', 20),
    ('coordinator', '/attendance?event_id=10009', 20),
    ('director', '/director_dash', 25), ('director', '/analytics?period=all', 25),
    ('director', '/analytics?view=historical', 15), ('director', '/annual-goals', 20),
    ('director', '/notifications', 8),
])
def test_large_populated_goal_query_budgets(benchmark_app, role, path, budget):
    client = signed_in_client(benchmark_app, role)
    with query_count(benchmark_app) as statements:
        response = client.get(path)
    assert response.status_code == 200
    assert len(statements) <= budget, (path, len(statements))
    assert len(response.data) < 180_000


def test_notification_pagination_has_global_unread_and_owner_scope(benchmark_app):
    with benchmark_app.app_context():
        person = User.query.filter_by(email='benchmark-0@example.test').one()
        identity, version = person.id, person.auth_version
    client = benchmark_app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(identity), _fresh=True, auth_version=version)
    seen = set()
    for number in range(1, 5):
        page = parse_html(client.get(f'/notifications?page={number}').get_data(as_text=True))
        records = page.all('article')
        assert len(records) == 25
        identifiers = {form.attrs['action'] for record in records for form in record.all('form')}
        assert not identifiers & seen
        seen.update(identifiers)
        assert page.one('nav', **{'aria-label': 'Notification pages'})
        assert 'Mark all as read' in page.text


def test_pagination_keeps_repeated_filters_and_cannot_replace_path_arguments(benchmark_app):
    with benchmark_app.app_context():
        target_id = AnnualTarget.query.filter_by(campus_id=None).first().id
    client = signed_in_client(benchmark_app, 'director')
    response = client.get(f'/annual-goals/targets/{target_id}/activities', query_string=[
        ('target_id', '999999'), ('_external', '1'), ('_anchor', 'elsewhere'), ('campus', '1'), ('campus', '2')])
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    href = page.one('nav', **{'aria-label': 'Linked goal activity pages'}).one('a', rel='next').attrs['href']
    destination = urlsplit(href)
    assert not destination.netloc and destination.path == f'/annual-goals/targets/{target_id}/activities'
    assert parse_qs(destination.query)['campus'] == ['1', '2']
    assert parse_qs(destination.query)['page'] == ['2']


def test_report_sql_pagination_and_batches_preserve_totals(benchmark_app):
    with benchmark_app.app_context():
        whole, expected = build_events_report()
        page, summary = build_events_report(limit=10, offset=10)
        assert page == whole[10:20] and summary == expected
        records, totals = batched_events_report()
        assert list(records) == whole and totals == expected
        for attention in ('pending_attendance', 'low_attendance', 'missed_targets'):
            full, expected = build_events_report(attention=attention)
            partial, totals = build_events_report(attention=attention, limit=10)
            assert partial == full[:10] and totals == expected


def test_attendance_save_only_changes_submitted_page_and_is_batched(benchmark_app):
    client = signed_in_client(benchmark_app, 'coordinator')
    with benchmark_app.app_context():
        campus = User.query.filter_by(role='coordinator').first().campus_id
        event = Event.query.filter(Event.campus_id == campus, Event.end_date < datetime.now()).first()
        registrations = Registration.query.filter_by(event_id=event.id).order_by(Registration.id).all()
        selected, untouched = registrations[0], registrations[1]
        identity, event_id = selected.id, event.id
        before = (untouched.id, untouched.status, untouched.attendance_record.status if untouched.attendance_record else None)
    with query_count(benchmark_app) as statements:
        response = client.post('/attendance?page=1', data=dict(event_id=event_id, registration_id=identity, status='present'))
    assert response.status_code == 302 and len(statements) <= 15
    with benchmark_app.app_context():
        selected = db.session.get(Registration, identity)
        assert selected.status == 'completed' and selected.attendance_record.status == 'present'
        untouched = db.session.get(Registration, before[0])
        assert (untouched.id, untouched.status, untouched.attendance_record.status if untouched.attendance_record else None) == before


def test_fifty_attendance_rows_use_single_statements_and_leave_next_page_unchanged(benchmark_app):
    client = signed_in_client(benchmark_app, 'coordinator')
    with benchmark_app.app_context():
        campus = User.query.filter_by(role='coordinator').first().campus_id
        activity = Event.query.filter(Event.campus_id == campus, Event.end_date < datetime.now()).first()
        activity_id = activity.id
        identities = [row[0] for row in db.session.query(Registration.id).filter_by(event_id=activity_id).order_by(Registration.id)]
        people = User.query.filter(User.role == 'volunteer',
            ~User.registrations.any(Registration.event_id == activity_id)).limit(5).all()
        extra = [Registration(user_id=person.id, event_id=activity_id, status='confirmed') for person in people]
        db.session.add_all(extra)
        db.session.commit()
        untouched = [registration.id for registration in extra]
        engine = db.engine
    writes = []
    def record(connection, cursor, sql, parameters, context, executemany):
        if sql.lstrip().upper().startswith(('UPDATE REGISTRATIONS', 'UPDATE ATTENDANCE', 'INSERT INTO ATTENDANCE')):
            writes.append((sql, executemany))
    sqlalchemy_event.listen(engine, 'before_cursor_execute', record)
    try:
        with query_count(benchmark_app) as statements:
            response = client.post('/attendance', data=dict(event_id=activity_id,
                registration_id=identities, status=['present'] * len(identities)))
        assert response.status_code == 302 and len(statements) <= 15
        assert writes and len(writes) <= 3 and not any(many for sql, many in writes)
        with benchmark_app.app_context():
            assert all(registration.certificate_eligible for registration in
                       Registration.query.filter(Registration.id.in_(identities)))
            assert all(registration.status == 'confirmed' and registration.attendance_record is None for registration in
                       Registration.query.filter(Registration.id.in_(untouched)))
    finally:
        sqlalchemy_event.remove(engine, 'before_cursor_execute', record)


@pytest.mark.parametrize('email', ['student@psu.edu', 'benchmark-500@example.test'])
def test_registration_cancellation_write_budgets_and_state(benchmark_app, email):
    volunteer = signed_in_client(benchmark_app, 'volunteer')
    coordinator = signed_in_client(benchmark_app, 'coordinator')
    with benchmark_app.app_context():
        person = User.query.filter_by(email=email).one()
        campus = User.query.filter_by(role='coordinator').first().campus_id
        event_id = Event.query.filter(Event.campus_id == campus, Event.date > datetime.now(),
            ~Event.registrations.any(Registration.user_id == person.id)).first().id
        person_id = person.id
        version = person.auth_version
    with volunteer.session_transaction() as session:
        session.update(_user_id=str(person_id), _fresh=True, auth_version=version)
    with query_count(benchmark_app) as statements:
        assert volunteer.post(f'/opportunities/register/{event_id}', data={'accept_agreement': 'yes'}).status_code == 302
    assert len(statements) <= 15
    with benchmark_app.app_context():
        registration = Registration.query.filter_by(user_id=person_id, event_id=event_id).one()
        identity = registration.id
        assert registration.status == 'confirmed'
    with query_count(benchmark_app) as statements:
        assert volunteer.post(f'/registrations/{identity}/cancel', data={'reason': 'Academic Conflict'}).status_code == 302
    assert len(statements) <= 15
    with benchmark_app.app_context():
        cancellation_id = CancellationRequest.query.filter_by(registration_id=identity, status='pending').one().id
    with query_count(benchmark_app) as statements:
        assert coordinator.post('/coordinator/cancellation-requests', data=dict(request_id=cancellation_id,
            decision='approved', review_note='Schedule confirmed')).status_code == 302
    assert len(statements) <= 15
    with benchmark_app.app_context():
        assert db.session.get(Registration, identity).status == 'cancelled'


def test_metrics_redact_parameters(benchmark_app, caplog):
    benchmark_app.config.update(PERFORMANCE_METRICS_ENABLED=True, PERFORMANCE_SLOW_QUERY_MS=0)
    client = signed_in_client(benchmark_app, 'director')
    with caplog.at_level(logging.INFO, logger=benchmark_app.logger.name):
        client.get('/director_dash?activity_name=private-person@example.test')
    records = [record.message for record in caplog.records if 'request_performance' in record.message]
    assert records and all('queries=' in text and 'sql_ms=' in text for text in records)
    assert not any('private-person' in text or 'SELECT ' in text or 'password' in text for text in records)
    benchmark_app.config['PERFORMANCE_METRICS_ENABLED'] = False


def test_request_reuse_reflects_next_committed_write(benchmark_app):
    from flask import template_rendered
    unread = []
    def capture(sender, template, context, **extra):
        unread.append(context['unread'])
    client = signed_in_client(benchmark_app, 'director')
    template_rendered.connect(capture, benchmark_app)
    try:
        assert client.get('/notifications').status_code == 200
        with benchmark_app.app_context():
            person = User.query.filter_by(role='director').one()
            db.session.add(Notification(user_id=person.id, title='Attendance recorded', message='Campus records updated.'))
            db.session.commit()
        assert client.get('/notifications').status_code == 200
        assert unread[1] == unread[0] + 1
    finally:
        template_rendered.disconnect(capture, benchmark_app)


def test_index_preview_idempotence_and_limited_rollback():
    instance = create_app('testing')
    with instance.app_context():
        assert len(migrate_indexes(db.engine, ':memory:')) == 8
        with pytest.raises(ValueError):
            migrate_indexes(db.engine, 'wrong')
        before = {table: inspect(db.engine).get_indexes(table) for table in INDEXES}
        assert before == {table: inspect(db.engine).get_indexes(table) for table in INDEXES}
        migrate_indexes(db.engine, ':memory:', dry_run=False)
        planned = migrate_indexes(db.engine, ':memory:', rollback=True)
        assert len(planned) == 8
        migrate_indexes(db.engine, ':memory:', dry_run=False, rollback=True)
        with db.engine.begin() as connection:
            connection.exec_driver_sql('CREATE INDEX qa_equivalent_date ON events (date, id, campus_id)')
        planned = migrate_indexes(db.engine, ':memory:')
        assert not any(index_name('events', ('date','id')) in statement for statement in planned)
        migrate_indexes(db.engine, ':memory:', dry_run=False)
        assert migrate_indexes(db.engine, ':memory:') == []
        db.session.remove()
        db.engine.dispose()
