"""Database-independent public error responses."""
from flask import jsonify, request, url_for
from flask_wtf.csrf import CSRFError

from app.models import db


ERRORS = {
    400: ('We couldn’t complete that request', 'Reopen the page and check your entries.'),
    403: ('You don’t have access to this page', 'Your account doesn’t have permission to view this page.'),
    404: ('This page couldn’t be found', 'The address may be incorrect, or the page may have moved.'),
    500: ('Something went wrong', 'We couldn’t load this page. Please try again in a few moments.'),
}


def register_error_handlers(app):
    def error_response(error):
        code = error.code
        title, message = ERRORS[code]
        if isinstance(error, CSRFError):
            message = 'Your form expired. Reopen the page and try again.'
        if code == 500:
            # Flask logs the original exception before invoking this handler.
            try:
                db.session.rollback()
            except Exception:
                app.logger.exception('Could not roll back the failed request transaction')
        response = error.get_response()
        accepts = request.accept_mimetypes
        wants_json = request.is_json or (
            accepts['application/json'] > accepts['text/html']
        )
        if wants_json:
            response.set_data(jsonify(error=message, code=code).get_data())
            response.content_type = 'application/json'
        else:
            # Normal context processors can load users, policies, or notifications.
            # Error rendering must remain independent of those database-backed paths.
            response.set_data(app.jinja_env.get_template('errors/error.html').render(
                code=code, title=title, message=message,
                home_url=url_for('home'), signin_url=url_for('auth.login')))
            response.content_type = 'text/html; charset=utf-8'
        response.headers['Cache-Control'] = 'no-store'
        return response

    for code in ERRORS:
        app.register_error_handler(code, error_response)
