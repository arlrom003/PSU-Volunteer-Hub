import json
from http.client import HTTPException
from unittest.mock import patch

import pytest
from flask import Flask

from app.services.email import send_email


@pytest.fixture
def brevo_app():
    app = Flask(__name__)
    app.config.update(MAIL_PROVIDER='brevo', BREVO_API_KEY='test-only-key',
                      MAIL_DEFAULT_SENDER='PSU Volunteer Hub <sender@example.test>',
                      MAIL_SUPPRESS_SEND=False, MAIL_TIMEOUT=15)
    with app.app_context():
        yield app


def test_brevo_uses_https_with_expected_message_and_no_smtp(brevo_app):
    with patch('app.services.email.HTTPSConnection') as https, patch('app.services.email.smtplib.SMTP') as smtp:
        connection = https.return_value
        connection.getresponse.return_value.status = 201
        send_email('recipient@example.test', 'Password recovery', 'Temporary password: test-only')
        https.assert_called_once_with('api.brevo.com', timeout=15)
        args, kwargs = connection.request.call_args
        assert args == ('POST', '/v3/smtp/email')
        assert kwargs['headers']['api-key'] == 'test-only-key'
        assert json.loads(kwargs['body']) == {
            'sender': {'name': 'PSU Volunteer Hub', 'email': 'sender@example.test'},
            'to': [{'email': 'recipient@example.test'}],
            'subject': 'Password recovery', 'textContent': 'Temporary password: test-only',
        }
        connection.close.assert_called_once()
        smtp.assert_not_called()


@pytest.mark.parametrize('status', [400, 401, 403, 429, 500])
def test_brevo_rejection_raises_for_existing_recovery_rollback(brevo_app, status):
    with patch('app.services.email.HTTPSConnection') as https:
        connection = https.return_value
        connection.getresponse.return_value.status = status
        with pytest.raises(OSError, match=f'HTTP {status}'):
            send_email('recipient@example.test', 'Reset', 'test-only')
        connection.close.assert_called_once()


@pytest.mark.parametrize('failure', [TimeoutError('timeout'), HTTPException('protocol failure')])
def test_brevo_connection_failures_raise_oserror_and_close(brevo_app, failure):
    with patch('app.services.email.HTTPSConnection') as https:
        connection = https.return_value
        connection.request.side_effect = failure
        with pytest.raises(OSError):
            send_email('recipient@example.test', 'Reset', 'test-only')
        connection.close.assert_called_once()


def test_brevo_requires_key_and_rejects_unknown_provider(brevo_app):
    with patch('app.services.email.HTTPSConnection') as https:
        brevo_app.config['BREVO_API_KEY'] = ''
        with pytest.raises(OSError, match='BREVO_API_KEY is required'):
            send_email('recipient@example.test', 'Reset', 'test-only')
        brevo_app.config['MAIL_PROVIDER'] = 'misspelled'
        with pytest.raises(OSError, match='MAIL_PROVIDER must be'):
            send_email('recipient@example.test', 'Reset', 'test-only')
        https.assert_not_called()


def test_suppression_prevents_brevo_calls_and_does_not_log_body(brevo_app, caplog):
    brevo_app.config['MAIL_SUPPRESS_SEND'] = True
    with patch('app.services.email.HTTPSConnection') as https:
        send_email('recipient@example.test', 'Reset', 'temporary-secret-test-only')
        https.assert_not_called()
        assert 'temporary-secret-test-only' not in caplog.text
        assert 'test-only-key' not in caplog.text
