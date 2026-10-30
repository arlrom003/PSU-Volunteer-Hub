from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import event as sqlalchemy_event

from app import create_app
from app.annual_goals import participation
from app.models import db
from app.models.audit import AuditLog
from app.models.event import Attendance, Event, ExternalParticipant, Registration
from app.models.user import User
from app.recommendation.analytics import AnalyticsAggregator
from tests.html_helpers import parse_html
from tests.test_app import app


REPORT_YEAR = (datetime.now() - timedelta(days=90)).year


@pytest.fixture(scope='module')
def system_app():
    instance = create_app('testing')
    original = User.set_password
    User.set_password = lambda self, password: setattr(self, 'password_hash', 'test-only-unusable')
    try:
        result = instance.test_cli_runner().invoke(
            args=['reset-and-seed-demo', '--database', ':memory:'],
            input='RESET DEMO local/:memory:\n')
        assert result.exit_code == 0, result.exception
    finally:
        User.set_password = original
    with instance.app_context():
        User.query.filter_by(email='student@psu.edu').one().sex = 'male'
        admin = User(name='Performance Admin', email='performance-admin@example.test',
                     role='admin', password_hash='test-only-unusable')
        db.session.add(admin)
        for index in range(52):
            db.session.add(User(name=f'Inactive {index}', email=f'inactive-{index}@example.test',
                password_hash='test-only-unusable', campus_id=1, _is_active=False,
                deactivated_at=datetime.now() - timedelta(days=40)))
            db.session.add(AuditLog(action='performance_check', actor=admin,
                target_type='User', target_id=index, created_at=datetime(2026, 1, 1)))
        db.session.commit()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.engine.dispose()


def signed_in_client(instance, role):
    client = instance.test_client()
    if role:
        with instance.app_context():
            user = User.query.filter_by(role=role, _is_active=True).first()
            identity, version = user.id, user.auth_version
        with client.session_transaction() as session:
            session['_user_id'] = str(identity)
            session['_fresh'] = True
            session['auth_version'] = version
    return client


@contextmanager
def query_count(instance):
    with instance.app_context():
        engine = db.engine
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    sqlalchemy_event.listen(engine, 'before_cursor_execute', record)
    try:
        yield statements
    finally:
        sqlalchemy_event.remove(engine, 'before_cursor_execute', record)


@pytest.mark.parametrize('role,path,budget', [
    (None, '/', 6), (None, '/opportunities', 7),
    ('volunteer', '/volunteer_dash', 40), ('volunteer', '/profile', 40),
    ('coordinator', '/coordinator_dash', 35), ('coordinator', '/coordinator_analytics', 30),
    ('director', f'/analytics?period=all&award_year={REPORT_YEAR}', 50),
    ('director', f'/director_dash?period=all&award_year={REPORT_YEAR}', 50),
    ('admin', '/admin_dash', 15), ('admin', '/admin_dash?tab=audit', 15),
])
def test_large_dataset_page_query_budgets(system_app, role, path, budget):
    client = signed_in_client(system_app, role)
    with query_count(system_app) as statements:
        response = client.get(path)
    assert response.status_code == 200
    assert len(statements) <= budget, (path, len(statements))
    if role == 'admin':
        assert len(response.data) < 100_000


@pytest.mark.parametrize('basis', ['registrations', 'verified_attendance', 'completed', 'unique_attendees'])
def test_participant_breakdown_uses_one_query(system_app, basis):
    with system_app.app_context(), query_count(system_app) as statements:
        result = participation(REPORT_YEAR, campus_id=1, basis=basis)
    assert result['total'] > 0
    assert len(statements) == 1


def test_awards_and_forecast_queries_are_bounded(system_app):
    with system_app.app_context(), query_count(system_app) as statements:
        awards = AnalyticsAggregator.award_leaderboards(REPORT_YEAR)
    assert len(awards['volunteers']) == 5
    assert len(statements) == 5
    with system_app.app_context(), query_count(system_app) as statements:
        forecast = AnalyticsAggregator.forecast_turnout(campus_id=1)
    assert forecast
    assert all(0 <= row['predicted_attendance_rate'] <= 1 for row in forecast)
    assert len(statements) == 4


@pytest.mark.parametrize('path', ['/static/styles/base.css', '/static/scripts/form-submit-state.js',
                                  '/static/assets/PSU-logo.png', '/favicon.ico'])
def test_public_assets_revalidate_without_user_queries(system_app, path):
    client = signed_in_client(system_app, 'admin')
    with query_count(system_app) as statements:
        response = client.get(path)
        cached = client.get(path, headers={'If-None-Match': response.headers['ETag']})
    assert response.status_code == 200
    assert cached.status_code == 304
    assert not response.cache_control.no_store
    assert not cached.cache_control.no_store
    assert not statements
    assert client.get('/admin_dash').cache_control.no_store
    assert client.get('/static/styles/missing.css').cache_control.no_store


def test_uploaded_files_still_use_no_store(system_app, tmp_path, monkeypatch):
    directory = tmp_path / 'uploads'
    directory.mkdir()
    (directory / 'example.txt').write_text('Synthetic upload', encoding='utf-8')
    monkeypatch.setattr(system_app, 'static_folder', str(tmp_path))
    response = signed_in_client(system_app, 'admin').get('/static/uploads/example.txt')
    assert response.status_code == 200
    assert response.cache_control.no_store


@pytest.mark.parametrize('tab,section_id,label', [
    ('users', 'user-management', 'User pages'),
    ('deactivated', 'deactivated-users', 'Deactivated user pages'),
    ('audit', 'activity-log', 'Activity log pages'),
])
def test_admin_pages_keep_filters_and_reach_all_rows(system_app, tab, section_id, label):
    client = signed_in_client(system_app, 'admin')
    url = f'/admin_dash?tab={tab}&campus_id=1'
    seen = []
    while url:
        response = client.get(url)
        assert response.status_code == 200
        page = parse_html(response.get_data(as_text=True))
        section = page.one('section', id=section_id)
        rows = section.one('tbody').all('tr')
        assert 1 <= len(rows) <= 25
        seen.extend(row.text for row in rows)
        navigation = section.one('nav', **{'aria-label': label})
        assert navigation.one('span', **{'aria-current': 'page'})
        for link in navigation.all('a'):
            query = parse_qs(urlsplit(link.attrs['href']).query)
            assert query['tab'] == [tab] and query['campus_id'] == ['1']
        links = navigation.all('a', rel='next')
        url = links[0].attrs['href'] if links else None
    assert len(seen) == len(set(seen))
    with system_app.app_context():
        expected = (AuditLog.query.count() if tab == 'audit' else User.query.filter_by(
            campus_id=1, _is_active=tab == 'users').count())
    assert len(seen) == expected
    assert client.get(f'/admin_dash?tab={tab}&campus_id=1&page=999').status_code == 302
    assert client.get(f'/admin_dash?tab={tab}&page=invalid').status_code == 200
    assert client.get(f'/admin_dash?tab={tab}&page=-1').status_code == 200


def test_empty_admin_page_and_role_boundary(system_app):
    response = signed_in_client(system_app, 'admin').get('/admin_dash?campus_id=999999')
    assert response.status_code == 200
    assert b'No users found.' in response.data
    assert b'aria-label="User pages"' not in response.data
    assert signed_in_client(system_app, 'volunteer').get('/admin_dash').status_code == 403


def test_award_counts_keep_year_role_campus_and_completion_rules(app):
    people = [User(name=name, email=f'award-{index}@example.test',
                   role='director' if index == 3 else 'volunteer',
                   campus_id=campus, password_hash='test-only-unusable')
              for index, (name, campus) in enumerate([
                  ('Alpha', 1), ('Beta', 2), ('Gamma', None), ('Director', 3)])]
    outsider = ExternalParticipant(id_number='performance-award-external')
    db.session.add_all([*people, outsider])
    db.session.flush()
    for year, campus, cases in [
        (2020, 1, [(0, 'completed'), (1, 'confirmed'), (2, 'completed'), (None, 'completed')]),
        (2020, 2, [(0, 'completed'), (1, 'completed'), (3, 'cancelled')]),
        (2019, 1, [(0, 'completed')]), (2021, 1, [(0, 'completed')]),
    ]:
        activity = Event(title='Award count check', description='Known counts',
                         date=datetime(year, 6, 1), campus_id=campus)
        db.session.add(activity)
        db.session.flush()
        for index, status in cases:
            registration = Registration(event_id=activity.id, status=status,
                user_id=people[index].id if index is not None else None,
                external_participant_id=outsider.id if index is None else None)
            db.session.add(registration)
            db.session.flush()
            db.session.add(Attendance(registration_id=registration.id, event_id=activity.id,
                user_id=registration.user_id, status='present'))
    db.session.commit()
    awards = AnalyticsAggregator.award_leaderboards(2020)
    assert awards['volunteers'] == [
        dict(name='Alpha', campus='Lingayen', attendance=2, completed=2, rank=1),
        dict(name='Beta', campus='Urdaneta', attendance=2, completed=1, rank=2),
        dict(name='Gamma', campus='Unassigned', attendance=1, completed=1, rank=3),
    ]
    assert awards['campuses'] == [
        dict(name='Urdaneta', registrations=2, attendance=3, rate=150.0, rank=1),
        dict(name='Lingayen', registrations=3, attendance=3, rate=100.0, rank=2),
    ]
    assert AnalyticsAggregator.award_leaderboards(2018) == dict(volunteers=[], campuses=[])


def test_forecast_and_attendance_summary_keep_cancelled_denominator(app):
    person = ExternalParticipant(id_number='performance-forecast-person')
    other = ExternalParticipant(id_number='performance-forecast-other')
    db.session.add_all([person, other])
    db.session.flush()
    for index, slots in enumerate([10, 20, 30]):
        activity = Event(title=f'Forecast past {index}', description='Known counts',
                         slots=slots, campus_id=5, date=datetime.now() - timedelta(days=index + 2))
        db.session.add(activity)
        db.session.flush()
        for number, participant in enumerate([person, other]):
            registration = Registration(event_id=activity.id, external_participant_id=participant.id,
                status='confirmed' if number else 'cancelled')
            db.session.add(registration)
            db.session.flush()
            if number < index:
                db.session.add(Attendance(registration_id=registration.id,
                    event_id=activity.id, status='present'))
    future = Event(title='Forecast future', description='Known prediction', slots=20,
                   campus_id=5, date=datetime.now() + timedelta(days=2))
    db.session.add(future)
    db.session.commit()
    forecast = AnalyticsAggregator.forecast_turnout(campus_id=5)
    assert len(forecast) == 1
    assert forecast[0]['predicted_attendance_rate'] == pytest.approx(0.5)
    summary = {row['event'].title: row for row in AnalyticsAggregator.attendance_summary(campus_id=5)}
    for index in range(3):
        assert summary[f'Forecast past {index}']['registered'] == 2
        assert summary[f'Forecast past {index}']['attended'] == index
        assert summary[f'Forecast past {index}']['rate'] == index * 50
