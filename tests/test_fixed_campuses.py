import pytest

from app import _seed_campuses
from app.campuses import PSU_CAMPUSES, PSU_CAMPUS_AFFILIATIONS, campus_affiliations, validate_catalogue
from app.models import db
from app.models.event import Campus
from tests.test_app import app, client, _create_user, _login_as
from app import create_app
from config import ProductionConfig


def test_partial_catalogue_keeps_ids_and_adds_missing(app):
    with app.app_context():
        original = Campus.query.filter_by(code='LINGAYEN').one().id
        Campus.query.filter_by(code='ALAMINOS').delete()
        db.session.commit()
        _seed_campuses(app)
        assert Campus.query.filter_by(code='LINGAYEN').one().id == original
        assert {(row.name, row.code) for row in validate_catalogue()} == set(PSU_CAMPUSES)
        _seed_campuses(app)
        assert Campus.query.count() == 9


def test_each_official_campus_has_fixed_registration_affiliations(app):
    with app.app_context():
        for name, code in PSU_CAMPUSES:
            campus = Campus.query.filter_by(code=code).one()
            assert campus_affiliations(campus) == list(PSU_CAMPUS_AFFILIATIONS[code])
            assert campus_affiliations(campus)


def test_registration_rejects_affiliation_from_another_campus(client, app):
    response = client.post('/auth/register', data={
        'first_name': 'Mismatch', 'last_name': 'User',
        'email': 'mismatch@example.test', 'password': '12345678',
        'password_confirmation': '12345678', 'id_number': 'MISMATCH-01',
        'volunteer_type': 'student', 'sex': 'prefer_not_to_say',
        'campus': '1', 'college_affiliation': 'College of Computing (CC)',
    })
    assert response.status_code == 200
    assert b'Select a College Affiliation for the selected campus.' in response.data


def test_custom_campus_blocks_seed_without_deleting_records(app):
    with app.app_context():
        db.session.add(Campus(name='Custom Campus', code='CUSTOM'))
        db.session.commit()
        with pytest.raises(ValueError, match=r'Custom Campus \(CUSTOM, ID'):
            _seed_campuses(app)
        assert Campus.query.filter_by(code='CUSTOM').one()
        assert Campus.query.count() == 10


@pytest.mark.parametrize('url', [
    '/admin_dash?campus_id=99999',
    '/admin_dash?campus_id=999999999999999999999999',
    '/analytics?campus=99999',
    '/analytics?campus=bad',
    '/reports/campus.csv?campus_id=99999',
])
def test_invalid_campus_choice_rejected(client, app, url):
    uid = _create_user(app, role='admin')
    _login_as(client, uid)
    assert client.get(url).status_code == 400


def test_campus_creation_disabled_and_cards_removed(client, app):
    uid = _create_user(app, role='admin')
    _login_as(client, uid)
    assert client.get('/admin/campuses/create').status_code == 410
    assert client.post('/admin/campuses/create', data={'name': 'Custom', 'code': 'CUSTOM'}).status_code == 410
    response = client.get('/admin_dash')
    assert b'<strong>Add Campus</strong>' not in response.data
    assert b'<strong>System Settings</strong>' not in response.data
    assert client.get('/settings').status_code == 200
    form = client.get('/admin/users/create').get_data(as_text=True)
    for name, code in PSU_CAMPUSES:
        assert f'>{name}</option>' in form


def test_sync_command_adds_missing_campus(app):
    with app.app_context():
        Campus.query.filter_by(code='ALAMINOS').delete()
        db.session.commit()
    result = app.test_cli_runner().invoke(args=['sync-campus-catalogue'])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert Campus.query.count() == 9


def test_production_startup_rejects_custom_catalogue(app, monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    path = tmp_path / 'campus-startup.sqlite'
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    Campus.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(Campus.__table__.insert().values(name='Custom Campus', code='CUSTOM'))
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', str(engine.url))
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {})
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'isolated-campus-startup-test')
    with pytest.raises(ValueError, match='Custom Campus'):
        create_app('production')
    with engine.connect() as connection:
        assert connection.execute(db.select(Campus.__table__.c.code)).scalar() == 'CUSTOM'
    engine.dispose()
