from datetime import datetime, timedelta
from hashlib import sha256
import threading
import time

import pytest
from werkzeug.exceptions import Forbidden

from app import create_app
from app.models import db
from app.models.event import ExternalParticipant, Registration
from app.models.user import AuthSecurityEvent, PasswordResetToken, User
from app.reports import csv_safe, render_pdf
from app.routes.events import _upsert_external_participant
from config import ProductionConfig
from tests.test_app import app, client, _create_user, _login_as


def call(app, client, method, path, **kwargs):
    with app.app_context():
        return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize('path', ['/coordinator_dash', '/coordinator_analytics',
                                 '/reports/events.csv', '/reports/events.pdf'])
def test_unassigned_coordinator_fails_closed(app, client, path):
    user_id = _create_user(app, email='unassigned@example.test', role='coordinator')
    _login_as(client, user_id)
    response = call(app, client, 'get', path)
    assert response.status_code == 403
    assert b'campus_total_attended' not in response.data


def test_external_person_cannot_be_read_or_mutated_across_campuses(app):
    with app.app_context():
        person = ExternalParticipant(id_number='campus-b-person', email='b@example.test')
        db.session.add(person)
        db.session.flush()
        db.session.add(Registration(external_participant_id=person.id, event_id=3))
        db.session.commit()
        with pytest.raises(Forbidden):
            _upsert_external_participant('campus-b-person', 1, name='attacker')
        assert person.name is None
        assert person.email == 'b@example.test'
        assert Registration.query.filter_by(external_participant_id=person.id).count() == 1
        assert _upsert_external_participant('campus-b-person', 2) is person
        fresh = _upsert_external_participant('brand-new', 1, name='New Person')
        assert fresh.name == 'New Person'
        with pytest.raises(Forbidden):
            _upsert_external_participant('brand-new', 2, email='attacker@example.test')
        assert fresh.email is None


@pytest.mark.parametrize('action', ['create', 'role', 'edit'])
def test_admin_cannot_assign_coordinator_without_campus(app, client, action):
    admin = _create_user(app, email='admin@example.test', role='admin')
    target = _create_user(app, email='target@example.test')
    _login_as(client, admin)
    path = {'create': '/admin/users/create',
            'role': f'/admin/users/role/{target}',
            'edit': f'/admin/users/{target}/edit'}[action]
    call(app, client, 'post', path, data={
        'name': 'New Coordinator', 'email': 'new@example.test',
        'password': 'password123', 'role': 'coordinator', 'campus_id': ''})
    with app.app_context():
        assert User.query.filter_by(email='new@example.test', role='coordinator').count() == 0
        assert db.session.get(User, target).role == 'volunteer'


def test_human_csv_export_escapes_formula_and_backup_preserves_value(app, client):
    import csv
    import io
    admin = _create_user(app, email='admin@example.test', role='admin')
    target = _create_user(app, email='target@example.test')
    with app.app_context():
        db.session.get(User, target).id_number = '=1+1'
        db.session.commit()
    _login_as(client, admin)
    response = call(app, client, 'get', '/admin/users/export.csv')
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert next(row for row in rows if row['email'] == 'target@example.test')['id_number'] == "'=1+1"
    from app.routes.admin import _backup_value
    assert _backup_value('=1+1') == '=1+1'


def test_deactivation_revokes_recovery_and_existing_session(app, client):
    admin = _create_user(app, email='admin@example.test', role='admin')
    target = _create_user(app, email='target@example.test', campus_id=1)
    old_client = app.test_client()
    _login_as(old_client, target)
    with app.app_context():
        db.session.add(PasswordResetToken(
            user_id=target, token_hash=sha256(b'old-temporary').hexdigest(),
            expires_at=datetime.utcnow() + timedelta(minutes=30)))
        db.session.commit()
    _login_as(client, admin)
    assert call(app, client, 'post', f'/admin/users/deactivate/{target}').status_code == 302
    assert call(app, client, 'post', f'/admin/users/{target}/reactivate').status_code == 302
    with app.app_context():
        assert PasswordResetToken.query.one().used_at is not None
        assert db.session.get(User, target).auth_version == 2
    assert call(app, old_client, 'get', '/profile').status_code == 302
    response = call(app, app.test_client(), 'post', '/auth/login', data={
        'identifier': 'target@example.test', 'password': 'old-temporary'})
    assert response.status_code == 200


@pytest.mark.parametrize('dimension, count', [('account', 4), ('source', 11)])
def test_recovery_independent_budgets(app, client, monkeypatch, dimension, count):
    dispatches = []
    monkeypatch.setattr('app.routes.auth._send_recovery_email_async',
                        lambda *args: dispatches.append(args))
    for i in range(count):
        email = f'user-{i if dimension == "source" else 0}@example.test'
        ip = f'192.0.2.{i + 1}' if dimension == 'account' else '192.0.2.1'
        call(app, client, 'post', '/auth/forgot-password', data={'email': email},
             environ_overrides={'REMOTE_ADDR': ip})
    with app.app_context():
        action = f'password_reset_{dimension}'
        assert AuthSecurityEvent.query.filter_by(action=action).count() == count - 1
    assert not dispatches


def test_recovery_does_not_wait_for_provider(app, client, monkeypatch):
    _create_user(app, email='active@example.test')
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def slow_provider(*args):
        started.set()
        release.wait(2)
        finished.set()
    monkeypatch.setattr('app.routes.auth.send_email', slow_provider)
    before = time.monotonic()
    try:
        response = call(app, client, 'post', '/auth/forgot-password',
                        data={'email': 'active@example.test'})
        assert started.wait(0.5)
        assert time.monotonic() - before < 1
        assert not finished.is_set()
        with app.app_context():
            assert PasswordResetToken.query.filter_by(used_at=None).count() == 1
        unknown = call(app, app.test_client(), 'post', '/auth/forgot-password',
                       data={'email': 'unknown@example.test'})
        assert (response.status_code, response.location, response.data) == (
            unknown.status_code, unknown.location, unknown.data)
    finally:
        release.set()
        assert finished.wait(1)


def test_recovery_dispatch_capacity_is_bounded(app, monkeypatch, caplog):
    from app.routes.auth import _send_recovery_email_async
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr('app.routes.auth._recovery_delivery_slots', slots)
    def forbidden_thread(**kwargs):
        raise AssertionError('Dispatch must not create more threads at capacity')
    monkeypatch.setattr('app.routes.auth.threading.Thread', forbidden_thread)
    _send_recovery_email_async(app, 'dummy@example.test', 'Recovery', 'dummy-secret')
    assert 'capacity reached' in caplog.text
    assert 'dummy-secret' not in caplog.text


def test_pdf_metadata_never_loads_resources(monkeypatch):
    import reportlab.lib.utils
    def forbidden(*args, **kwargs):
        raise AssertionError('Report metadata attempted a resource read')
    monkeypatch.setattr(reportlab.lib.utils, 'open_for_read', forbidden)
    payload = '<img src="file:///scratch/private.png"/>'
    meta = dict(title=payload, scope=payload, role_label=payload,
                date_range='All dates', category=payload, generated='2026-10-29',
                historical_note=payload, activity_name=payload)
    summary = dict(event_count=0, total_registrations=0, total_psu=0,
                   total_external=0, total_attended=0, total_cancelled=0,
                   total_completed=0)
    result = render_pdf([], summary, meta)
    assert result.startswith(b'%PDF-')
    assert b'/Subtype /Image' not in result
    meta['category'] = 'General'
    assert render_pdf([], summary, meta).startswith(b'%PDF-')


@pytest.mark.parametrize('role, path', [
    ('coordinator', '/reports/events.pdf'),
    ('director', '/reports/university.pdf'),
])
def test_pdf_routes_treat_category_as_text(app, client, monkeypatch, role, path):
    import reportlab.lib.utils
    user = _create_user(app, email=f'{role}@example.test', role=role, campus_id=1)
    _login_as(client, user)
    def forbidden(*args, **kwargs):
        raise AssertionError('PDF export attempted a resource read')
    monkeypatch.setattr(reportlab.lib.utils, 'open_for_read', forbidden)
    response = call(app, client, 'get', path, query_string={
        'category': '<img src="file:///scratch/private.png"/>'})
    assert response.status_code == 200
    assert response.data.startswith(b'%PDF-')
    assert b'/Subtype /Image' not in response.data


@pytest.mark.parametrize('value', ['=1+1', '+1', '-1', '@SUM(A1)', '\t=1', '\r=1', '\n=1'])
def test_spreadsheet_cells_are_text(value):
    assert csv_safe(value) == "'" + value
    assert csv_safe('Normal') == 'Normal'
    assert csv_safe(42) == 42


@pytest.mark.parametrize('count', [0, -1, 11, '1'])
def test_production_rejects_invalid_proxy_count(monkeypatch, count):
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'dummy-test-only')
    monkeypatch.setattr(ProductionConfig, 'TRUSTED_PROXY_COUNT', count)
    with pytest.raises(ValueError, match='TRUSTED_PROXY_COUNT'):
        create_app('production')


def test_forwarded_host_is_ignored(monkeypatch):
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {})
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'dummy-test-only')
    monkeypatch.setattr(ProductionConfig, 'TRUSTED_PROXY_COUNT', 1)
    production = create_app('production')
    @production.route('/proxy-test')
    def inspect_proxy():
        from flask import request
        return {'host': request.host, 'ip': request.remote_addr}
    response = production.test_client().get('/proxy-test', headers={
        'X-Forwarded-Host': 'attacker.invalid',
        'X-Forwarded-For': '203.0.113.9, 10.0.0.5'})
    assert response.json == {'host': 'localhost', 'ip': '10.0.0.5'}
