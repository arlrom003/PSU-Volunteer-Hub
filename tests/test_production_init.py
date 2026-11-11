"""Exercise production provisioning only against isolated empty SQLite schemas."""
import pytest
import re
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.models import db
from app.models.event import Campus, Event, SdgGoal
from app.models.user import User, Skill, Interest
from config import ProductionConfig


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {})
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'isolated-provisioning-tests-only')
    return create_app('production')


def invoke(production, answer='y', name='Initial Admin', email='admin@example.org', password='OnlyForTests-2026!'):
    return production.test_cli_runner().invoke(args=['init-production', '--database', ':memory:'],
        input=f'{answer}\n{name}\n{email}\n{password}\n{password}\n')


def test_initializes_reference_data_and_only_one_admin(production):
    result = invoke(production)
    assert result.exit_code == 0, result.output
    assert 'OnlyForTests-2026!' not in result.output
    with production.app_context():
        administrator = User.query.one()
        assert administrator.role == 'admin' and administrator.email == 'admin@example.org'
        assert administrator.check_password('OnlyForTests-2026!')
        assert administrator.password_hash != 'OnlyForTests-2026!'
        assert Campus.query.count() == 9 and SdgGoal.query.count() == 17
        assert Skill.query.count() > 0 and Interest.query.count() > 0
        assert Event.query.count() == 0
    client = production.test_client()
    page = client.get('/auth/login', base_url='https://localhost').get_data(as_text=True)
    token = re.search(r'const token = "([^"]+)"', page).group(1)
    response = client.post('/auth/login', base_url='https://localhost', headers={'Referer': 'https://localhost/auth/login'}, data={
        'identifier': 'admin@example.org', 'password': 'OnlyForTests-2026!', 'csrf_token': token})
    assert response.status_code == 302 and '/admin_dash' in response.location
    repeated = invoke(production)
    assert repeated.exit_code != 0 and 'not empty' in repeated.output
    with production.app_context():
        assert User.query.count() == 1 and Event.query.count() == 0


@pytest.mark.parametrize('kwargs', [{'answer': 'n'}, {'name': ' '}, {'email': 'not-an-email'}, {'password': 'password'}])
def test_cancel_or_invalid_inputs_leave_schema_empty(production, kwargs):
    result = invoke(production, **kwargs)
    assert result.exit_code != 0
    with production.app_context():
        assert db.inspect(db.engine).get_table_names() == []


def test_wrong_database_or_environment_refused(production):
    runner = production.test_cli_runner()
    result = runner.invoke(args=['init-production', '--database', 'wrong'])
    assert result.exit_code != 0 and 'does not match' in result.output
    production.config['APP_ENV'] = 'development'
    result = invoke(production)
    assert result.exit_code != 0 and 'production configuration' in result.output
    with production.app_context():
        assert db.inspect(db.engine).get_table_names() == []


def test_unrelated_existing_table_is_not_touched(production):
    with production.app_context():
        db.session.execute(text('CREATE TABLE sentinel (value INTEGER)'))
        db.session.execute(text('INSERT INTO sentinel VALUES (42)'))
        db.session.commit()
    result = invoke(production)
    assert result.exit_code != 0 and 'not empty' in result.output
    with production.app_context():
        assert db.inspect(db.engine).get_table_names() == ['sentinel']
        assert db.session.execute(text('SELECT value FROM sentinel')).scalar_one() == 42


def test_failure_does_not_drop_or_silently_resume_schema(production, monkeypatch):
    def fail(*args, **kwargs):
        raise SQLAlchemyError('simulated fixture failure')
    monkeypatch.setattr('app._seed_sdgs', fail)
    result = invoke(production)
    assert result.exit_code != 0 and 'Schema may remain' in result.output
    with production.app_context():
        assert db.inspect(db.engine).get_table_names()
        assert User.query.count() == 0 and Campus.query.count() == 0
    assert 'not empty' in invoke(production).output


def test_existing_view_is_refused(production):
    with production.app_context():
        db.session.execute(text('CREATE VIEW sentinel AS SELECT 42 AS value'))
        db.session.commit()
    assert 'not empty' in invoke(production).output
    with production.app_context():
        assert db.inspect(db.engine).get_table_names() == []
        assert db.session.execute(text('SELECT value FROM sentinel')).scalar_one() == 42


def test_mismatched_password_confirmation_does_not_create_schema(production):
    result = production.test_cli_runner().invoke(args=['init-production', '--database', ':memory:'],
        input='y\nInitial Admin\nadmin@example.org\nOnlyForTests-2026!\nDifferent-password\n')
    assert result.exit_code != 0
    with production.app_context():
        assert db.inspect(db.engine).get_table_names() == []
