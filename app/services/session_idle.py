"""Validate inactivity using server time and Flask's signed session cookie."""
# ponytail: no central revocation store; add shared server-side sessions if required.
import math
import time

from flask import current_app, flash, jsonify, redirect, request, session, url_for
from flask_login import logout_user

IDLE_MESSAGE = 'Your session timed out due to inactivity. Please sign in again.'


def session_status():
    return {
        'server_time': time.time(),
        'expires_at': session['last_activity_at'] + current_app.config['SESSION_IDLE_TIMEOUT_SECONDS'],
        'warning_seconds': current_app.config['SESSION_IDLE_WARNING_SECONDS'],
    }


def end_session(message):
    session.clear()
    logout_user()
    flash(message, 'session-expired')
    if request.endpoint == 'auth.session_activity':
        response = jsonify(sign_in_url=url_for('auth.login'))
        response.status_code = 401
        response.headers['Cache-Control'] = 'no-store'
        return response
    response = redirect(url_for('auth.login'))
    response.headers['Cache-Control'] = 'no-store'
    return response


def check_inactivity():
    if request.endpoint in ('static', 'favicon'):
        return None
    now = time.time()
    last = session.get('last_activity_at')
    # Existing signed-in cookies get a grace window when this feature is deployed.
    if last is None:
        session['last_activity_at'] = now
    elif (isinstance(last, bool) or not isinstance(last, (int, float))
          or not math.isfinite(last) or last > now
          or now - last >= current_app.config['SESSION_IDLE_TIMEOUT_SECONDS']):
        return end_session(IDLE_MESSAGE)
    # Status reads and HEAD requests never keep unattended sessions alive.
    if request.method != 'HEAD' and not (
            request.endpoint == 'auth.session_activity' and request.method == 'GET'):
        session['last_activity_at'] = now
    return None
