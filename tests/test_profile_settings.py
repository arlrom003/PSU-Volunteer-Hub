"""Independent account edits, credential isolation, and preserved participation."""
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy.exc import SQLAlchemyError

from tests.test_app import app, client, _create_user, _login_as
from app.models import db
from app.models.user import User, AuthSecurityEvent, PasswordResetToken, SystemSetting
from app.models.audit import AuditLog
from app.models.event import Event, Registration, Attendance
from app.campuses import campus_rows, campus_affiliations

OLD = 'OriginalPassword1!'
NEW = 'UpdatedPassword2!'


@pytest.fixture
def member(app, client):
    identity = _create_user(app, password=OLD, campus_id=1)
    _login_as(client, identity)
    return identity


def password_form():
    return dict(current_password=OLD, new_password=NEW, password_confirmation=NEW)


@pytest.mark.parametrize('kind', ['student', 'faculty', 'staff', None])
def test_name_is_independent_and_scoped(app, client, member, kind):
    other = _create_user(app, email='another-profile@example.test', name='Unchanged')
    with app.app_context():
        db.session.get(User, member).volunteer_type = kind
        db.session.commit()
    response = client.post('/profile/name', data=dict(name='  María O’Reyes-Santos  ',
        user_id=other, email='forged@example.test', role='admin', campus_id=999999))
    assert response.status_code == 303
    assert response.location.endswith('/profile#change-name')
    with app.app_context():
        user = db.session.get(User, member)
        assert user.name == 'María O’Reyes-Santos' and user.role == 'volunteer'
        assert user.email == 'test@example.com' and user.campus_id == 1
        assert db.session.get(User, other).name == 'Unchanged'
        assert AuditLog.query.filter_by(action='profile_name_changed', actor_id=member, target_id=member).count() == 1


@pytest.mark.parametrize('name', ['', ' ', 'x'*101, 'Invalid\x00Name', 'Line\nBreak'])
def test_invalid_names_keep_existing_identity(app, client, member, name):
    assert client.post('/profile/name', data={'name': name}).status_code == 422
    with app.app_context():
        assert db.session.get(User, member).name == 'Test User'


def test_campus_preserves_history_and_event_credit(app, client, member):
    from tests.test_annual_goals import target
    from app.annual_goals import summary
    from app.models.annual_plan import AnnualActivityMapping
    with app.app_context():
        campus = next(c for c in campus_rows() if c.id != 1)
        new_id, college, campus_name = campus.id, campus_affiliations(campus)[0], campus.name
        activity = db.session.get(Event, 1)
        activity.date = datetime.now()-timedelta(hours=1)
        hosting_campus = activity.campus_id
        registration = Registration(user_id=member, event_id=1, status='completed')
        db.session.add(registration)
        db.session.flush()
        attendance = Attendance(registration_id=registration.id, event_id=1, user_id=member, status='present')
        db.session.add(attendance)
        db.session.commit()
        registration_id, attendance_id = registration.id, attendance.id
        goal = target(campus=hosting_campus, basis='unique_attendees', value=1)
        db.session.add(AnnualActivityMapping(target_id=goal.id, event_id=1))
        db.session.commit()
        assert summary(campus_id=hosting_campus)['met'] == 1
    response = client.post('/profile/campus', data=dict(campus_id=new_id, college_affiliation=college))
    assert response.status_code == 303
    with app.app_context():
        user = db.session.get(User, member)
        assert user.campus_id == new_id and user.college_affiliation == college
        assert db.session.get(Event, 1).campus_id == hosting_campus
        assert db.session.get(Registration, registration_id).certificate_eligible
        assert db.session.get(Attendance, attendance_id).status == 'present'
        assert summary(campus_id=hosting_campus)['met'] == 1
        audit = AuditLog.query.filter_by(action='profile_campus_changed').one()
        assert json.loads(audit.details) == dict(campus_from=1, campus_to=new_id)
    assert campus_name.encode() in client.get('/profile').data


@pytest.mark.parametrize('campus,college', [('bad', 'Invalid'), ('999999', 'Invalid'), ('', ''), ('1', 'Wrong college')])
def test_invalid_campus_pair_returns_field_errors(app, client, member, campus, college):
    response = client.post('/profile/campus', data=dict(campus_id=campus, college_affiliation=college))
    assert response.status_code == 422
    assert b'data-profile-errors' in response.data
    with app.app_context():
        assert db.session.get(User, member).campus_id == 1
        assert AuditLog.query.filter_by(action='profile_campus_changed').count() == 0


def test_password_keeps_current_session_and_revokes_others(app, client, member):
    other = app.test_client()
    _login_as(other, member)
    with app.app_context():
        token = PasswordResetToken(user_id=member, token_hash='a'*64,
                                   expires_at=datetime.utcnow()+timedelta(hours=1))
        db.session.add(token)
        db.session.commit()
    assert client.post('/profile/password', data=password_form()).status_code == 303
    with app.app_context():
        user = db.session.get(User, member)
        assert user.check_password(NEW) and not user.check_password(OLD) and user.auth_version == 2
        assert PasswordResetToken.query.filter_by(user_id=member, used_at=None).count() == 0
        audit = AuditLog.query.filter_by(action='profile_password_changed').one()
        assert audit.details is None and audit.target_id == member
    with client.session_transaction() as saved:
        assert saved['auth_version'] == 2
        assert OLD not in str(dict(saved)) and NEW not in str(dict(saved))
    assert client.get('/profile').status_code == 200
    assert other.get('/profile').location.endswith('/auth/login')


@pytest.mark.parametrize('current,new,confirmation', [
    ('wrong', NEW, NEW), (OLD, 'weak', 'weak'), (OLD, NEW, 'Mismatch'), (OLD, OLD, OLD)])
def test_password_errors_are_atomic_and_never_refilled(app, client, member, current, new, confirmation):
    response = client.post('/profile/password', data=dict(current_password=current,
        new_password=new, password_confirmation=confirmation))
    assert response.status_code == 422
    assert f'value="{new}"'.encode() not in response.data
    assert f'value="{current}"'.encode() not in response.data
    with app.app_context():
        user = db.session.get(User, member)
        assert user.check_password(OLD) and user.auth_version == 1


def test_password_uses_configured_minimum(app, client, member):
    with app.app_context():
        row = SystemSetting.query.filter_by(key='default_password_length').first()
        if row is None:
            db.session.add(SystemSetting(key='default_password_length', value='24'))
        else:
            row.value = '24'
        db.session.commit()
    response = client.post('/profile/password', data=password_form())
    assert response.status_code == 422 and b'at least 24 characters' in response.data


def test_password_failure_limit_and_expiry(app, client, member):
    values = dict(current_password='wrong', new_password=NEW, password_confirmation=NEW)
    for _ in range(5):
        assert client.post('/profile/password', data=values).status_code == 422
    assert client.post('/profile/password', data=password_form()).status_code == 429
    assert client.post('/profile/name', data={'name': 'Still editable'}).status_code == 303
    with app.app_context():
        assert AuthSecurityEvent.query.filter_by(action='password_change').count() == 5
        AuthSecurityEvent.query.filter_by(action='password_change').update(
            {'created_at': datetime.utcnow()-timedelta(minutes=16)})
        db.session.commit()
    assert client.post('/profile/password', data=password_form()).status_code == 303


def test_change_between_guard_and_row_lock_is_rejected(app, client, member):
    @app.before_request
    def concurrent_change():
        from flask import request
        if request.endpoint == 'volunteer.change_password':
            user = db.session.get(User, member)
            user.set_password('ConcurrentPassword3!')
            user.auth_version += 1
            db.session.commit()
    response = client.post('/profile/password', data=password_form())
    assert response.status_code == 302 and response.location.endswith('/auth/login')
    with app.app_context():
        assert db.session.get(User, member).check_password('ConcurrentPassword3!')


@pytest.mark.parametrize('endpoint,values', [
    ('name', {'name': 'Unsaved name'}),
    ('campus', {'campus_id': 2, 'college_affiliation': 'College of Computing (CC)'}),
    ('password', password_form())])
def test_save_failure_rolls_back_and_logs_no_credentials(app, client, member, monkeypatch, caplog, endpoint, values):
    with app.app_context():
        before = db.session.get(User, member)
        original = before.name, before.campus_id, before.password_hash, before.auth_version
        db.session.add(PasswordResetToken(user_id=member, token_hash='b'*64,
            expires_at=datetime.utcnow()+timedelta(hours=1)))
        db.session.commit()
        if endpoint == 'campus':
            target = next(c for c in campus_rows() if c.id != before.campus_id)
            values = dict(campus_id=target.id, college_affiliation=campus_affiliations(target)[0])
    def fail():
        raise SQLAlchemyError('sensitive-bind-placeholder')
    with monkeypatch.context() as patch:
        patch.setattr(db.session, 'commit', fail)
        response = client.post('/profile/'+endpoint, data=values)
    assert response.status_code == 422
    with app.app_context():
        user = db.session.get(User, member)
        assert (user.name, user.campus_id, user.password_hash, user.auth_version) == original
        assert AuditLog.query.filter(AuditLog.action.like('profile_%_changed')).count() == 0
        assert PasswordResetToken.query.filter_by(user_id=member, used_at=None).count() == 1
    assert OLD not in caplog.text and NEW not in caplog.text
    assert 'sensitive-bind-placeholder' not in caplog.text


@pytest.mark.parametrize('role', [None, 'admin', 'director', 'coordinator'])
def test_endpoint_access_boundaries(app, client, role):
    if role:
        _login_as(client, _create_user(app, role=role))
    for endpoint in ('name', 'campus', 'password'):
        response = client.post('/profile/'+endpoint)
        assert response.status_code == (403 if role else 302)


def test_csrf_is_required(app, client, member):
    app.config['WTF_CSRF_ENABLED'] = True
    for endpoint in ('name', 'campus', 'password'):
        assert client.post('/profile/'+endpoint).status_code == 400
