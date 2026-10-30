"""Error responses must work even when users, context processors, and SQL fail."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Blueprint, Flask, abort, redirect, jsonify
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, text
from werkzeug.exceptions import NotFound

from app.errors import register_error_handlers
from app.models import db


@pytest.fixture
def error_app():
    root = Path(__file__).resolve().parents[1]
    app = Flask('error-test', template_folder=str(root/'templates'), static_folder=str(root/'static'))
    app.config.update(TESTING=True, SECRET_KEY='error-test-only', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      PROPAGATE_EXCEPTIONS=False, WTF_CSRF_ENABLED=False)
    db.init_app(app)
    CSRFProtect(app)
    auth = Blueprint('auth', __name__)
    auth.add_url_rule('/login', 'login', lambda: 'Sign in')
    app.register_blueprint(auth)
    app.add_url_rule('/', 'home', lambda: 'Home')
    register_error_handlers(app)

    @app.route('/error/<int:code>')
    def fail(code):
        abort(code, description='PRIVATE SQL/password/traceback details')

    @app.route('/unexpected')
    def unexpected():
        raise RuntimeError('PRIVATE database connection details')

    @app.route('/database-failure')
    def database_failure():
        db.session.execute(text('SELECT * FROM missing_private_table'))
        return 'unreachable'

    @app.route('/form', methods=['POST'])
    def form():
        return 'Form accepted'

    @app.route('/existing-json')
    def existing_json():
        return jsonify(error='Existing API validation message'), 400

    @app.route('/existing-redirect')
    def existing_redirect():
        return redirect('/')

    @app.route('/missing-record')
    def missing_record():
        raise NotFound(response=app.response_class('PRIVATE', status=404, headers={'Retry-After':'30'}))

    @app.context_processor
    def broken_context():
        raise AssertionError('Error rendering must not invoke normal context processors')

    return app


@pytest.mark.parametrize('code,heading', [(400,'complete that request'),(403,'access to this page'),
                                        (404,'page couldn’t be found'),(500,'Something went wrong')])
def test_custom_html_status_recovery_and_no_details(error_app, code, heading):
    client = error_app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = 'unavailable-user'
    response = client.get(f'/error/{code}')
    body = response.get_data(as_text=True)
    assert response.status_code == code and heading in body
    assert body.count('<h1>') == 1
    assert 'PSU Volunteer Hub' in body and 'Return home' in body
    assert ('>Sign in<' in body) == (code != 500)
    assert 'PRIVATE' not in body and 'traceback' not in body
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'role-sidebar' not in body and 'session-idle.js' not in body


def test_unknown_url_missing_record_and_headers(error_app):
    client = error_app.test_client()
    response = client.get('/does-not-exist')
    assert response.status_code == 404 and b'error-code' in response.data
    response = client.get('/missing-record')
    assert response.status_code == 404 and response.headers['Retry-After'] == '30'
    assert b'PRIVATE' not in response.data


@pytest.mark.parametrize('headers', [{'Accept':'application/json'}, {'Content-Type':'application/json'},
                                    {'Accept':'application/json;q=1, text/html;q=0.5'}])
def test_json_clients_get_safe_json(error_app, headers):
    response = error_app.test_client().get('/error/403', headers=headers)
    assert response.status_code == 403 and response.is_json
    assert response.json == {'code':403,'error':'Your account doesn’t have permission to view this page.'}


def test_html_wildcards_and_explicit_responses_stay_compatible(error_app):
    client = error_app.test_client()
    assert client.get('/error/404',headers={'Accept':'*/*'}).mimetype == 'text/html'
    assert client.get('/existing-json').json == {'error':'Existing API validation message'}
    assert client.get('/existing-redirect').status_code == 302


def test_csrf_uses_safe_expired_form_message(error_app):
    error_app.config['WTF_CSRF_ENABLED'] = True
    response = error_app.test_client().post('/form')
    assert response.status_code == 400 and b'Your form expired.' in response.data
    assert b'CSRF token' not in response.data
    response = error_app.test_client().post('/form', headers={'Accept':'application/json'})
    assert response.status_code == 400 and response.json['code'] == 400


def test_unexpected_error_is_logged_and_transaction_rolled_back(error_app, monkeypatch, caplog):
    rollback = Mock()
    monkeypatch.setattr(db.session, 'rollback', rollback)
    response = error_app.test_client().get('/unexpected')
    assert response.status_code == 500 and b'PRIVATE' not in response.data
    rollback.assert_called_once()
    assert 'PRIVATE database connection details' in caplog.text


def test_database_failure_runs_no_rendering_queries(error_app):
    queries = []
    with error_app.app_context():
        event.listen(db.engine,'before_cursor_execute',lambda *args:queries.append(args[2]))
    response = error_app.test_client().get('/database-failure')
    assert response.status_code == 500 and b'Something went wrong' in response.data
    assert len(queries) == 1
    assert b'missing_private_table' not in response.data


def test_rollback_failure_still_has_a_safe_screen(error_app, monkeypatch):
    monkeypatch.setattr(db.session,'rollback',Mock(side_effect=RuntimeError('PRIVATE rollback details')))
    response = error_app.test_client().get('/unexpected')
    assert response.status_code == 500 and b'PRIVATE' not in response.data


def test_testing_can_still_propagate(error_app):
    error_app.config['PROPAGATE_EXCEPTIONS'] = True
    with pytest.raises(RuntimeError, match='PRIVATE'):
        error_app.test_client().get('/unexpected')


def test_factory_handles_user_loader_failure_and_keeps_assets_available(monkeypatch):
    from app import create_app
    from app.models.user import User
    app = create_app('testing')
    app.config['PROPAGATE_EXCEPTIONS'] = False
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = '123'
        session['auth_version'] = 1
    get = Mock(side_effect=RuntimeError('PRIVATE user database unavailable'))
    monkeypatch.setattr(db.session,'get',get)
    response = client.get('/coordinator_dash')
    assert response.status_code == 500 and b'PRIVATE' not in response.data
    get.assert_called_once_with(User,123)
    get.reset_mock()
    assert client.get('/static/styles/errors.css').status_code == 200
    assert client.get('/does-not-exist').status_code == 404
    get.assert_not_called()


@pytest.mark.parametrize('environment,enabled,propagates',[
    ('development','false',False),('development','true',True),('production','true',False)])
def test_debugger_setting_is_development_only(monkeypatch,environment,enabled,propagates):
    import app as application
    from config import DevelopmentConfig, ProductionConfig
    monkeypatch.setenv('DEV_ERROR_DEBUGGER',enabled)
    for config in (DevelopmentConfig,ProductionConfig):
        monkeypatch.setattr(config,'SQLALCHEMY_DATABASE_URI','sqlite:///:memory:')
    monkeypatch.setattr(ProductionConfig,'SECRET_KEY','isolated-error-config-test')
    monkeypatch.setattr(db,'create_all',lambda:None)
    for name in ['_seed_campuses','_seed_interests_skills','_seed_sdgs','_seed_events','_seed_users']:
        monkeypatch.setattr(application,name,lambda *args,**kwargs:None)
    instance = application.create_app(environment)
    assert instance.config['PROPAGATE_EXCEPTIONS'] is propagates
    assert instance.config['DEV_ERROR_DEBUGGER'] is propagates
    @instance.route('/unexpected-error-config-test')
    def fail():
        raise RuntimeError('PRIVATE configured debug exception')
    if propagates:
        with pytest.raises(RuntimeError):
            instance.test_client().get('/unexpected-error-config-test')
    else:
        response = instance.test_client().get('/unexpected-error-config-test')
        assert response.status_code == 500 and b'PRIVATE' not in response.data
