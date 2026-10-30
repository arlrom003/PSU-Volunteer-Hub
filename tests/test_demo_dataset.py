"""Destructive demo CLI checks use only SQLite with foreign keys enabled."""
from datetime import datetime

import pytest
from sqlalchemy import select

from app import create_app
from app.models import db
from app.models.audit import AuditLog
from app.models.event import (Attendance, CancellationRequest, Campus, Event,
                              ExternalParticipant, Registration, event_sdgs)
from app.models.user import User
from app.demo_dataset import DEMO_SERVICE_ID, PREFIX


@pytest.fixture
def app():
    instance = create_app('testing')
    with instance.app_context():
        db.session.remove()
        with db.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
    yield instance
    with instance.app_context():
        db.session.remove()
        db.engine.dispose()


def invoke(app, confirmation=None, *options):
    return app.test_cli_runner().invoke(
        args=['reset-and-seed-demo', '--database', ':memory:', *options],
        input=confirmation)


def test_refuses_wrong_service_database_account_and_confirmation(app, monkeypatch):
    app.testing = False
    monkeypatch.setenv('RAILWAY_SERVICE_ID', 'main-service')
    assert 'approved Railway demo' in invoke(app).output
    monkeypatch.setenv('RAILWAY_SERVICE_ID', DEMO_SERVICE_ID)
    result = app.test_cli_runner().invoke(args=['reset-and-seed-demo', '--database', 'wrong'])
    assert result.exit_code != 0 and 'does not match' in result.output
    app.testing = True
    with app.app_context():
        count = Event.query.count()
        coordinator = User.query.filter_by(email='coordinator@psu.edu').one()
        coordinator.role = 'volunteer'
        db.session.commit()
    result = invoke(app)
    assert result.exit_code != 0 and 'must have role coordinator' in result.output
    with app.app_context():
        coordinator = User.query.filter_by(email='coordinator@psu.edu').one()
        coordinator.role = 'coordinator'
        db.session.commit()
    assert invoke(app, 'NO\n').exit_code != 0
    result = invoke(app, None, '--dry-run')
    assert result.exit_code == 0, (result.output, result.exception)
    with app.app_context():
        assert Event.query.count() == count


def test_replacement_counts_links_preservation_repeat_and_rollback(app, monkeypatch):
    with app.app_context():
        passwords = {u.email: (u.id, u.password_hash) for u in User.query.all()}
        ordinary_ids = {e.id for e in Event.query.all()}
        coordinator = User.query.filter_by(email='coordinator@psu.edu').one()
        coordinator.campus_id = None
        old = Event(title='[Demo Analytics] Old fixture', description='old', date=datetime.now())
        db.session.add(old)
        participant = ExternalParticipant(id_number='DEMO-EXT-001', name='Previous fixture')
        registration = Registration(event=old, external_participant=participant)
        db.session.add(Attendance(registration=registration, event=old))
        db.session.commit()
    # Hashing speed is irrelevant to this database transaction test.
    monkeypatch.setattr(User, 'set_password', lambda self, password: setattr(self, 'password_hash', 'test-only-unusable-hash'))
    for iteration in range(2):
        result = invoke(app, 'RESET DEMO local/:memory:\n')
        assert result.exit_code == 0, (result.output, result.exception)
        with app.app_context():
            events = Event.query.filter(Event.title.startswith(PREFIX)).all()
            ids = [e.id for e in events]
            assert len(events) == 200
            assert Registration.query.filter(Registration.event_id.in_(ids)).count() == 5000
            assert Attendance.query.filter(Attendance.event_id.in_(ids)).count() == 4000
            assert CancellationRequest.query.count() == 150
            assert ExternalParticipant.query.count() == 200
            assert AuditLog.query.filter_by(action='synthetic_demo_fixture').count() == 200
            assert len(db.session.execute(select(event_sdgs).where(event_sdgs.c.event_id.in_(ids))).all()) == 600
            assert User.query.filter(User.email.like('volunteer-%@demo.invalid')).count() == 749
            assert {u.sex for u in User.query.filter(User.email.like('volunteer-%@demo.invalid')).all()} == {'male', 'female', 'prefer_not_to_say'}
            assert {u.email: (u.id, u.password_hash) for u in User.query.filter(User.email.in_(passwords)).all()} == passwords
            assert {e.id for e in Event.query.filter(Event.id.in_(ordinary_ids)).all()} == ordinary_ids
            assert not Event.query.filter(Event.title.startswith('[Demo Analytics]')).count()
            assert User.query.filter_by(email='coordinator@psu.edu').one().campus_id in {c.id for c in Campus.query.all()}
            assert any(e.date > datetime.now() and e.slots_remaining() == 0 and e.slots > 0 for e in events)
            assert any(e.date > datetime.now() and e.slots_remaining() > 0 for e in events)
            assert any(0 < len(e.attendance_records) < len(e.registrations) for e in events)
            assert all(r.registered_at <= datetime.now() for e in events for r in e.registrations)
            assert all(r.registration.status == ('cancelled' if r.status == 'approved' else 'confirmed') for r in CancellationRequest.query.all())
        if iteration == 0:
            client = app.test_client()
            assert client.get('/opportunities').status_code == 200
            for email, paths in (
                ('director@psu.edu', ('/director_dash', '/analytics', '/reports/university.csv')),
                ('coordinator@psu.edu', ('/coordinator_dash', '/coordinator_analytics')),
            ):
                with app.app_context():
                    user = User.query.filter_by(email=email).one()
                    user_id, version = user.id, user.auth_version
                with client.session_transaction() as session:
                    session.clear()
                    session['_user_id'] = str(user_id)
                    session['_fresh'] = True
                    session['auth_version'] = version
                for path in paths:
                    response = client.get(path)
                    assert response.status_code == 200, (path, response.status_code)
    with app.app_context():
        ids_before = {e.id for e in Event.query.all()}
    def fail(*args, **kwargs):
        raise RuntimeError('Injected fixture failure')
    monkeypatch.setattr('app._seed_sdgs', fail)
    result = invoke(app, 'RESET DEMO local/:memory:\n')
    assert result.exit_code != 0
    with app.app_context():
        assert {e.id for e in Event.query.all()} == ids_before
        assert Attendance.query.count() == 4000
        assert ExternalParticipant.query.count() == 200


def test_refuses_external_participant_used_outside_fixture(app):
    with app.app_context():
        other_event = Event.query.first()
        participant = ExternalParticipant(id_number='DEMO-EXT-001')
        db.session.add(Registration(event=other_event, external_participant=participant))
        db.session.commit()
    result = invoke(app, None, '--dry-run')
    assert result.exit_code != 0 and 'non-demo registrations' in result.output
