"""Production startup must never initialize schema, demo accounts or events."""
import runpy
from pathlib import Path

import pytest
import app as application
from sqlalchemy.exc import OperationalError
from app.models import db
from config import DevelopmentConfig, ProductionConfig


@pytest.fixture
def production_settings(monkeypatch):
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {})
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'isolated-production-startup-test-only')


@pytest.mark.parametrize('environment_selected', [False, True])
def test_production_startup_does_not_touch_database(monkeypatch, production_settings, environment_selected):
    def forbidden(*args, **kwargs):
        pytest.fail('Production startup attempted database initialization/seeding')
    monkeypatch.setattr(db, 'create_all', forbidden)
    for name in ('_seed_campuses', '_seed_interests_skills', '_seed_sdgs', '_seed_events', '_seed_users'):
        monkeypatch.setattr(application, name, forbidden)
    monkeypatch.setenv('APP_ENV', 'production')
    instance = application.create_app() if environment_selected else application.create_app('production')
    assert not instance.debug
    assert instance.config['SESSION_COOKIE_SECURE']
    with instance.app_context():
        assert db.inspect(db.engine).get_table_names() == []


@pytest.mark.parametrize('setting', ['SECRET_KEY', 'SQLALCHEMY_DATABASE_URI'])
def test_missing_production_settings_fail_closed(monkeypatch, production_settings, setting):
    monkeypatch.setattr(ProductionConfig, setting, None)
    with pytest.raises(ValueError):
        application.create_app('production')


def test_unknown_environment_does_not_fall_back_to_development(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'prodution')
    with pytest.raises(ValueError, match='APP_ENV'):
        application.create_app()


def test_wsgi_always_selects_production(monkeypatch):
    sentinel = object()
    calls = []
    def factory(environment):
        calls.append(environment)
        return sentinel
    monkeypatch.setattr(application, 'create_app', factory)
    monkeypatch.setenv('APP_ENV', 'development')
    result = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'wsgi.py'))
    assert calls == ['production'] and result['app'] is sentinel


def test_direct_production_launch_refuses_development_server(monkeypatch, production_settings):
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(SystemExit, match='production WSGI'):
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app.py'), run_name='__main__')


def test_development_keeps_local_demo_initialization(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setattr(DevelopmentConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    instance = application.create_app()
    assert instance.debug
    with instance.app_context():
        assert application.User.query.count() == 6
        assert application.Event.query.count() == 9


@pytest.mark.parametrize('code', [2002, 2003, 2006, 2013])
def test_production_recovers_from_brief_database_outage(
        monkeypatch, production_settings, caplog, code):
    inspect_database = db.inspect
    attempts, pauses = [], []

    def temporarily_unavailable(engine):
        attempts.append(1)
        if len(attempts) < 3:
            raise OperationalError(None, None, Exception(code, 'private-driver-details'))
        return inspect_database(engine)

    def no_schema_writes(*args, **kwargs):
        pytest.fail('Startup retry attempted to create tables')

    monkeypatch.setattr(db, 'inspect', temporarily_unavailable)
    monkeypatch.setattr(db, 'create_all', no_schema_writes)
    monkeypatch.setattr(application, 'sleep', pauses.append)
    instance = application.create_app('production')

    assert len(attempts) == 3
    assert pauses == [2, 2]
    assert 'private-driver-details' not in caplog.text
    with instance.app_context():
        assert inspect_database(db.engine).get_table_names() == []


def test_production_still_fails_when_database_never_recovers(
        monkeypatch, production_settings):
    attempts, pauses = [], []
    failure = OperationalError(None, None, Exception(2002, 'connection refused'))

    def unavailable(engine):
        attempts.append(1)
        raise failure

    monkeypatch.setattr(db, 'inspect', unavailable)
    monkeypatch.setattr(application, 'sleep', pauses.append)
    with pytest.raises(OperationalError) as raised:
        application.create_app('production')
    assert raised.value is failure
    assert len(attempts) == 5
    assert pauses == [2, 2, 2, 2]


@pytest.mark.parametrize('code', [1045, 1049, 1146, 'database is locked'])
def test_production_does_not_retry_permanent_or_non_mysql_errors(
        monkeypatch, production_settings, code):
    attempts, pauses = [], []
    failure = OperationalError(None, None, Exception(code, 'permanent failure'))

    def invalid_configuration(engine):
        attempts.append(1)
        raise failure

    monkeypatch.setattr(db, 'inspect', invalid_configuration)
    monkeypatch.setattr(application, 'sleep', pauses.append)
    with pytest.raises(OperationalError) as raised:
        application.create_app('production')
    assert raised.value is failure
    assert len(attempts) == 1
    assert not pauses


def test_production_retries_catalogue_connection_failure_with_fresh_session(
        monkeypatch, production_settings):
    from types import SimpleNamespace
    import app.campuses as campuses

    sessions, pauses = [], []

    def validate():
        sessions.append(db.session())
        assert db.session.execute(db.text('SELECT 1')).scalar() == 1
        if len(sessions) == 1:
            raise OperationalError(None, None, Exception(2013, 'connection lost'))

    monkeypatch.setattr(db, 'inspect', lambda engine: SimpleNamespace(has_table=lambda name: True))
    monkeypatch.setattr(campuses, 'validate_catalogue', validate)
    monkeypatch.setattr(application, 'sleep', pauses.append)
    application.create_app('production')
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert pauses == [2]


def test_production_does_not_skip_invalid_catalogue(monkeypatch, production_settings):
    from types import SimpleNamespace
    import app.campuses as campuses

    pauses = []

    def invalid_catalogue():
        raise ValueError('Unsupported PSU campus records')

    monkeypatch.setattr(db, 'inspect', lambda engine: SimpleNamespace(has_table=lambda name: True))
    monkeypatch.setattr(campuses, 'validate_catalogue', invalid_catalogue)
    monkeypatch.setattr(application, 'sleep', pauses.append)
    with pytest.raises(ValueError, match='Unsupported PSU campus records'):
        application.create_app('production')
    assert not pauses
