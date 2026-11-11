"""Optional real row-lock race on a dedicated local MySQL/MariaDB schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url


@pytest.mark.parametrize('scenario', ['success', 'throttled'])
def test_concurrent_password_changes_serialize(monkeypatch, scenario):
    value = os.getenv('PROFILE_TEST_DATABASE_URL')
    if not value:
        pytest.skip('Set PROFILE_TEST_DATABASE_URL to a disposable local psu_profile_* schema.')
    url = make_url(value)
    assert url.get_backend_name() in ('mysql', 'mariadb')
    assert url.host in ('localhost', '127.0.0.1') and url.database.startswith('psu_profile_')
    from config import TestingConfig
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', value)
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_ENGINE_OPTIONS', dict(
        pool_size=4, max_overflow=0, pool_timeout=5, connect_args={'connect_timeout': 5}), raising=False)
    from flask import request
    from app import create_app
    from app.models import db
    from app.models.user import User, PasswordResetToken, AuthSecurityEvent
    from app.models.audit import AuditLog
    app = create_app('testing')
    with app.app_context():
        user = User(name='Concurrent Participant', email=f'race-{uuid4().hex}@example.test',
                    role='volunteer', sex='prefer_not_to_say', campus_id=1)
        user.set_password('OriginalPassword1!')
        db.session.add(user)
        db.session.flush()
        identity = user.id
        subject = AuthSecurityEvent.subject(f'password_change|{identity}')
        if scenario == 'throttled':
            db.session.add_all([AuthSecurityEvent(action='password_change', subject_hash=subject)
                                for _ in range(4)])
        db.session.add(PasswordResetToken(user_id=identity, token_hash=uuid4().hex*2,
            expires_at=datetime.utcnow()+timedelta(hours=1)))
        db.session.commit()
    barrier = Barrier(2)
    @app.before_request
    def align_requests():
        if request.endpoint == 'volunteer.change_password':
            barrier.wait(timeout=15)
    def change(password):
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(_user_id=str(identity), _fresh=True, auth_version=1)
        return password, client.post('/profile/password', data=dict(
            current_password='incorrect' if scenario == 'throttled' else 'OriginalPassword1!', new_password=password,
            password_confirmation=password)).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change, ('ConcurrentNewPassword2!', 'ConcurrentNewPassword3!')))
        assert sorted(status for _, status in results) == ([422, 429] if scenario == 'throttled' else [302, 303])
        with app.app_context():
            user = db.session.get(User, identity)
            if scenario == 'throttled':
                assert user.auth_version == 1 and user.check_password('OriginalPassword1!')
                assert AuthSecurityEvent.query.filter_by(action='password_change', subject_hash=subject).count() == 5
                assert PasswordResetToken.query.filter_by(user_id=identity, used_at=None).count() == 1
            else:
                winner = next(password for password, status in results if status == 303)
                assert user.auth_version == 2 and user.check_password(winner)
                assert AuditLog.query.filter_by(action='profile_password_changed', target_id=identity).count() == 1
                assert PasswordResetToken.query.filter_by(user_id=identity, used_at=None).count() == 0
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
