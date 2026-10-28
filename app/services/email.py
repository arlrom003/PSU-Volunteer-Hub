"""Email delivery used for security notifications."""
import json
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from http.client import HTTPSConnection, HTTPException

from flask import current_app


def send_email(recipient, subject, body):
    """Send email, or log it locally when delivery is intentionally suppressed."""
    if current_app.config.get('MAIL_SUPPRESS_SEND'):
        current_app.logger.info('Suppressed email to %s: %s', recipient, subject)
        return
    provider = current_app.config.get('MAIL_PROVIDER', 'smtp')
    if provider == 'brevo':
        api_key = current_app.config.get('BREVO_API_KEY')
        if not api_key:
            raise OSError('BREVO_API_KEY is required for Brevo delivery')
        name, address = parseaddr(current_app.config['MAIL_DEFAULT_SENDER'])
        payload = json.dumps({
            'sender': {'name': name or 'PSU Volunteer Hub', 'email': address},
            'to': [{'email': recipient}], 'subject': subject, 'textContent': body,
        }).encode('utf-8')
        connection = HTTPSConnection('api.brevo.com', timeout=current_app.config['MAIL_TIMEOUT'])
        try:
            connection.request('POST', '/v3/smtp/email', body=payload, headers={
                'api-key': api_key, 'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
            response = connection.getresponse()
            response.read()
            if response.status != 201:
                raise OSError(f'Brevo email delivery failed (HTTP {response.status})')
        except HTTPException:
            raise OSError('Brevo email delivery connection failed') from None
        finally:
            connection.close()
        return
    if provider != 'smtp':
        raise OSError('MAIL_PROVIDER must be smtp or brevo')
    use_ssl = current_app.config.get('MAIL_USE_SSL')
    if use_ssl and current_app.config.get('MAIL_USE_TLS'):
        raise OSError('Enable either MAIL_USE_SSL or MAIL_USE_TLS, not both')
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = current_app.config['MAIL_DEFAULT_SENDER']
    message['To'] = recipient
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    options = {'timeout': current_app.config['MAIL_TIMEOUT']}
    if use_ssl:
        options['context'] = ssl.create_default_context()
    with smtp_class(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'], **options) as smtp:
        if current_app.config.get('MAIL_USE_TLS'):
            smtp.starttls(context=ssl.create_default_context())
        if current_app.config.get('MAIL_USERNAME'):
            smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        smtp.send_message(message)
