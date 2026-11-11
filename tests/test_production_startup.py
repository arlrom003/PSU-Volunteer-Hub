"""Production startup must never initialize schema, demo accounts or events."""
import runpy
from pathlib import Path

import pytest
import app as application
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
