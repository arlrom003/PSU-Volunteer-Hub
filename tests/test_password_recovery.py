import re
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import MagicMock, patch

import pytest

from app.models import db
from app.models.user import PasswordResetToken, User
from app.services.email import send_email
from tests.test_app import app, client, _create_user


@pytest.fixture
def recovery(app, monkeypatch):
    user_id = _create_user(app, email='recovery@example.test')
    messages = []
    monkeypatch.setattr('app.routes.auth.send_email', lambda *args: messages.append(args))
    return user_id, messages


def request(app, client, method, path, **kwargs):
    with app.app_context():
        return getattr(client, method)(path, **kwargs)


def issue(app, client, messages):
    response = request(app, client, 'post', '/auth/forgot-password',
                       data={'email': ' RECOVERY@EXAMPLE.TEST '})
    assert response.location == '/auth/login'
    return re.search(r'Temporary password: (\S+)', messages[-1][2])[1]


def test_temporary_password_requires_new_password_then_becomes_unusable(app, client, recovery):
    user_id, messages = recovery
    temporary = issue(app, client, messages)
    assert messages[0][0] == 'recovery@example.test'
    assert '30 minutes' in messages[0][2]
    assert temporary not in request(app, client, 'get', '/auth/login').get_data(as_text=True)
    with app.app_context():
        record = PasswordResetToken.query.one()
        assert record.token_hash == sha256(temporary.encode()).hexdigest()
        assert db.session.get(User, user_id).check_password('password123')
    response = request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': temporary})
    assert response.location == '/auth/reset-password'
    assert response.headers['Cache-Control'] == 'no-store'
    with client.session_transaction() as saved:
        assert '_user_id' not in saved
        assert temporary not in str(dict(saved))
    assert '/auth/login' in request(app, client, 'get', '/dashboard').location
    response = request(app, client, 'get', '/auth/reset-password')
    assert b'New password' in response.data
    assert response.headers['Cache-Control'] == 'no-store'
    for password, confirmation in [('short', 'short'), ('newpassword123', 'different'),
                                    (temporary, temporary)]:
        response = request(app, client, 'post', '/auth/reset-password', data={
            'password': password, 'password_confirmation': confirmation})
        assert b'aria-invalid="true"' in response.data
        with app.app_context():
            assert db.session.get(User, user_id).check_password('password123')
    response = request(app, client, 'post', '/auth/reset-password', data={
        'password': 'newpassword123', 'password_confirmation': 'newpassword123'})
    assert response.location == '/auth/login'
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.check_password('newpassword123')
        assert not user.check_password('password123')
        assert user.auth_version == 2
        assert PasswordResetToken.query.one().used_at is not None
    assert request(app, client, 'get', '/auth/reset-password').location == '/auth/forgot-password'
    assert request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': temporary}).status_code == 200
    assert request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': 'newpassword123'}).status_code == 302


@pytest.mark.parametrize('state', ['expired', 'used', 'inactive', 'wrong-account'])
def test_temporary_password_rejects_invalid_credentials(app, client, recovery, state):
    user_id, messages = recovery
    temporary = issue(app, client, messages)
    identifier = 'recovery@example.test'
    with app.app_context():
        record = PasswordResetToken.query.one()
        if state == 'expired':
            record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        elif state == 'used':
            record.used_at = datetime.utcnow()
        elif state == 'inactive':
            db.session.get(User, user_id).is_active = False
        else:
            _create_user(app, email='another@example.test')
            identifier = 'another@example.test'
        db.session.commit()
    response = request(app, client, 'post', '/auth/login', data={
        'identifier': identifier, 'password': temporary})
    assert b'Invalid email/ID or password.' in response.data
    with client.session_transaction() as saved:
        assert 'password_reset_hash' not in saved


def test_latest_password_invalidates_earlier_recovery_sessions(app, client, recovery):
    _, messages = recovery
    first = issue(app, client, messages)
    request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': first})
    second = issue(app, client, messages)
    assert first != second
    assert request(app, client, 'get', '/auth/reset-password').location == '/auth/forgot-password'
    assert request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': first}).status_code == 200
    assert request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': second}).location == '/auth/reset-password'


def test_expiry_is_rechecked_after_temporary_sign_in(app, client, recovery):
    _, messages = recovery
    temporary = issue(app, client, messages)
    request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': temporary})
    with app.app_context():
        PasswordResetToken.query.one().expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    assert request(app, client, 'post', '/auth/reset-password', data={
        'password': 'newpassword123', 'password_confirmation': 'newpassword123'}).location == '/auth/forgot-password'


def test_delivery_failure_preserves_current_and_previous_temporary_password(app, client, recovery, monkeypatch):
    user_id, messages = recovery
    first = issue(app, client, messages)
    def fail(*args):
        raise OSError('SMTP unavailable')
    monkeypatch.setattr('app.routes.auth.send_email', fail)
    response = request(app, client, 'post', '/auth/forgot-password',
                       data={'email': 'recovery@example.test'})
    assert response.location == '/auth/login'
    with app.app_context():
        assert PasswordResetToken.query.count() == 1
        assert PasswordResetToken.query.one().used_at is None
        assert db.session.get(User, user_id).check_password('password123')
    assert request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': first}).location == '/auth/reset-password'


def test_unknown_inactive_and_throttled_requests_do_not_send_mail(app, client, recovery):
    user_id, messages = recovery
    for email in ['missing@example.test', 'recovery@example.test']:
        if email.startswith('recovery'):
            with app.app_context():
                db.session.get(User, user_id).is_active = False
                db.session.commit()
        response = request(app, client, 'post', '/auth/forgot-password', data={'email': email}, follow_redirects=True)
        assert b'If an active account uses that email' in response.data
    assert not messages
    with app.app_context():
        db.session.get(User, user_id).is_active = True
        db.session.commit()
    for _ in range(4):
        request(app, client, 'post', '/auth/forgot-password', data={'email': 'recovery@example.test'})
    assert len(messages) == 2


@pytest.mark.parametrize('email', ['', 'invalid', 'a b@example.test'])
def test_reset_validates_email_on_server(app, client, email):
    response = request(app, client, 'post', '/auth/forgot-password', data={'email': email})
    assert response.status_code == 400
    assert b'aria-invalid="true"' in response.data


def test_recovery_forms_require_csrf(app, client, recovery):
    _, messages = recovery
    temporary = issue(app, client, messages)
    request(app, client, 'post', '/auth/login', data={
        'identifier': 'recovery@example.test', 'password': temporary})
    app.config['WTF_CSRF_ENABLED'] = True
    assert request(app, client, 'post', '/auth/forgot-password', data={'email': 'recovery@example.test'}).status_code == 400
    assert request(app, client, 'post', '/auth/reset-password', data={
        'password': 'newpassword123', 'password_confirmation': 'newpassword123'}).status_code == 400


@pytest.mark.parametrize('status', [201, 401])
def test_recovery_persists_credential_only_after_brevo_accepts(app, client, recovery, monkeypatch, status):
    user_id, _ = recovery
    app.config.update(MAIL_PROVIDER='brevo', BREVO_API_KEY='test-only-key', MAIL_SUPPRESS_SEND=False)
    monkeypatch.setattr('app.routes.auth.send_email', send_email)
    with patch('app.services.email.HTTPSConnection') as https:
        connection = https.return_value
        connection.getresponse.return_value.status = status
        response = request(app, client, 'post', '/auth/forgot-password',
                           data={'email': 'recovery@example.test'})
        assert response.location == '/auth/login'
        assert connection.request.call_args.args == ('POST', '/v3/smtp/email')
    with app.app_context():
        assert PasswordResetToken.query.count() == (1 if status == 201 else 0)
        assert db.session.get(User, user_id).check_password('password123')


@pytest.mark.parametrize('transport', ['tls', 'ssl', 'suppressed'])
def test_smtp_delivery_transport(app, transport):
    app.config.update(MAIL_SUPPRESS_SEND=transport == 'suppressed',
                      MAIL_USE_TLS=transport == 'tls', MAIL_USE_SSL=transport == 'ssl',
                      MAIL_SERVER='smtp.example.test', MAIL_PORT=465 if transport == 'ssl' else 587,
                      MAIL_USERNAME='sender@example.test', MAIL_PASSWORD='test-only-secret')
    with patch('app.services.email.smtplib.SMTP') as plain, patch('app.services.email.smtplib.SMTP_SSL') as secure:
        connection = MagicMock()
        selected = secure if transport == 'ssl' else plain
        selected.return_value.__enter__.return_value = connection
        with app.app_context():
            send_email('recipient@example.test', 'Test subject', 'Temporary password: test-only')
        if transport == 'suppressed':
            plain.assert_not_called()
            secure.assert_not_called()
            return
        assert selected.call_args.kwargs['timeout'] == 15
        if transport == 'tls':
            assert connection.starttls.call_args.kwargs['context'].check_hostname
        else:
            assert selected.call_args.kwargs['context'].check_hostname
            connection.starttls.assert_not_called()
        connection.login.assert_called_once_with('sender@example.test', 'test-only-secret')
        message = connection.send_message.call_args.args[0]
        assert message['To'] == 'recipient@example.test'
        assert 'test-only' in message.get_content()
