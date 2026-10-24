import pytest
import re
import io
import csv
from html import unescape
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit
from flask_login.utils import encode_cookie
from app import create_app
from app.models import db
from app.models.user import (User, VolunteerProfile, SystemSetting, Skill, Interest,
                             PasswordResetToken)
from app.models.event import (Event, EventAnnouncement, Registration,
                              Attendance, Campus, ExternalParticipant, Milestone,
                              CancellationRequest)
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.models.policy import (TermsRevision, TermsAcceptance, PrivacyRevision,
                               PrivacyAcknowledgement)
from app.recommendation.engine import (
    _cosine_similarity,
    bootstrap_from_event,
    get_recommendations,
)
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from tests.html_helpers import parse_html, form_with_control, form_values


# â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.fixture
def app():
    app = create_app('testing')
    app.config['SERVER_NAME'] = 'localhost'

    with app.app_context():
        # Replace the cached engine with an in-memory engine
        new_engine = create_engine('sqlite:///:memory:')
        db._app_engines[app][None] = new_engine
        db.create_all()
        _seed_campuses()
        _seed_events()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


# â”€â”€ Seed helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _seed_campuses():
    campuses = [
        Campus(name='Lingayen', code='LINGAYEN'),
        Campus(name='Urdaneta', code='URDANETA'),
        Campus(name='Asingan', code='ASINGAN'),
        Campus(name='Bayambang', code='BAYAMBANG'),
        Campus(name='Binmaley', code='BINMALEY'),
        Campus(name='Infanta', code='INFANTA'),
        Campus(name='San Carlos', code='SANCARLOS'),
        Campus(name='Santa Maria', code='STAMARIA'),
        Campus(name='Alaminos', code='ALAMINOS'),
    ]
    for c in campuses:
        db.session.add(c)
    db.session.commit()


def _seed_events():
    events = [
        Event(title='Youth Coding Mentor', description='Help students learn Python.',
              date=datetime.now() + timedelta(days=7),
              required_skills='Teaching, Python, Communication', slots=20,
              campus_id=1, category='Education & Literacy'),
        Event(title='Green Campus Initiative', description='Tree planting.',
              date=datetime.now() + timedelta(days=14),
              required_skills='Environmental Conservation, Agriculture', slots=50,
              campus_id=1, category='Environment'),
        Event(title='Community Food Drive', description='Distribute relief packages.',
              date=datetime.now() + timedelta(days=10),
              required_skills='Organizational, Communication', slots=30,
              campus_id=2, category='Community Development'),
        Event(title='Rural Literacy Program', description='Teach reading.',
              date=datetime.now() + timedelta(days=21),
              required_skills='Teaching, Tutoring, Communication', slots=15,
              campus_id=1, category='Education & Literacy'),
        Event(title='Disaster Response Training', description='First aid workshop.',
              date=datetime.now() + timedelta(days=5),
              required_skills='Medical, First Aid', slots=40,
              campus_id=3, category='Disaster Response'),
        Event(title='Community IT Support Workshop', description='Digital literacy.',
              date=datetime.now() + timedelta(days=30),
              required_skills='IT, Computer Skills, Teaching', slots=25,
              campus_id=4, category='Technology & Digital'),
        Event(title='Coastal Cleanup Drive', description='Preserve coastline.',
              date=datetime.now() + timedelta(days=3),
              required_skills='Environmental Conservation, Teamwork', slots=100,
              campus_id=1, category='Environment'),
        Event(title='Community Wellness Fair', description='Free health mission.',
              date=datetime.now() + timedelta(days=45),
              required_skills='Medical, First Aid, Organizational', slots=60,
              campus_id=7, category='Health & Wellness'),
        Event(title='Sustainable Farming Demo', description='Organic cultivation.',
              date=datetime.now() + timedelta(days=60),
              required_skills='Agriculture, Environmental Conservation', slots=30,
              campus_id=8, category='Environment'),
    ]
    for e in events:
        db.session.add(e)
    db.session.commit()


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _create_user(app, email='test@example.com', password='password123',
                 role='volunteer', name='Test User', campus_id=None,
                 sex='prefer_not_to_say'):
    with app.app_context():
        user = User(
            name=name,
            email=email,
            role=role,
            campus_id=campus_id,
            sex=sex,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _login_as(client, user_id):
    """Set Flask-Login session directly (avoids cookie issues between tests)."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
        sess['auth_version'] = 1


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# A. App Initialization
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAppInit:
    def test_app_creates(self, app):
        assert app is not None
        assert app.testing

    def test_db_tables_exist(self, app):
        with app.app_context():
            for tbl in ('users', 'events', 'campuses', 'registrations', 'attendance', 'volunteer_profiles', 'milestones', 'recommendation_logs', 'analytics_summaries'):
                assert tbl in db.metadata.tables, f'Table {tbl} not found'

    def test_nine_campuses_seeded(self, app):
        with app.app_context():
            assert Campus.query.count() == 9

    def test_nine_events_seeded(self, app):
        with app.app_context():
            assert Event.query.count() == 9


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# B. Authentication
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAuth:
    def test_interest_cards_use_native_labels_without_scripts(self, client, app):
        with app.app_context():
            db.session.add(Interest(name='Education & Literacy'))
            db.session.add(Skill(name='Teaching/Tutoring'))
            db.session.commit()

        resp = client.get('/auth/interests')
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'class="choice choice--interest"' in body
        assert 'choice-group__hit' not in body
        assert 'Select the skills you can contribute.' in body
        assert "document.querySelectorAll('.choice input')" not in body

    def test_interests_keep_only_related_skills(self, client, app):
        with app.app_context():
            catalog_entries = (
                (Interest, 'Education & Literacy'),
                (Interest, 'Environment'),
                (Skill, 'Teaching/Tutoring'),
                (Skill, 'Environmental Conservation'),
            )
            for model, name in catalog_entries:
                if not model.query.filter_by(name=name).first():
                    db.session.add(model(name=name))
            db.session.commit()
            education = Interest.query.filter_by(name='Education & Literacy').one()
            teaching = Skill.query.filter_by(name='Teaching/Tutoring').one()
            conservation = Skill.query.filter_by(name='Environmental Conservation').one()
            education_id = str(education.id)
            teaching_id = str(teaching.id)
            conservation_id = str(conservation.id)

        response = client.post('/auth/interests', data={
            'interests': education_id,
            'skills': [teaching_id, conservation_id],
        })

        assert response.status_code == 302
        with client.session_transaction() as saved_session:
            assert saved_session['selected_interests'] == [education_id]
            assert saved_session['selected_skills'] == [teaching_id]

    def test_register_get(self, client):
        resp = client.get('/auth/register')
        assert resp.status_code == 200

    def test_signup_shows_email_example_and_prefer_not_to_say(self, client):
        body = client.get('/auth/register').get_data(as_text=True)
        assert 'placeholder="00ur0000@psu.edu.ph"' in body
        assert 'value="prefer_not_to_say"' in body

    def test_register_creates_user(self, client, app):
        resp = client.post('/auth/register', data={
            'first_name': 'Alice', 'last_name': 'Test',
            'email': 'alice@test.com',
            'password': 'secret123',
            'account_type': 'volunteer', 'id_number': '21-0001',
            'campus': '1', 'volunteer_type': 'student',
            'sex': 'female',
            'college_affiliation': 'College of Computing Sciences',
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            u = User.query.filter_by(email='alice@test.com').first()
            assert u is not None
            assert u.role == 'volunteer'
            assert u.sex == 'female'

    def test_register_accepts_prefer_not_to_say(self, client, app):
        response = client.post('/auth/register', data={
            'first_name': 'Private', 'last_name': 'Volunteer',
            'email': 'private@test.com', 'password': 'secret123',
            'id_number': '21-0003', 'campus': '1',
            'volunteer_type': 'student', 'sex': 'prefer_not_to_say',
            'college_affiliation': 'College of Computing Sciences',
        })
        assert response.status_code == 302
        with app.app_context():
            assert User.query.filter_by(
                email='private@test.com').one().sex == 'prefer_not_to_say'

    def test_register_rejects_unknown_sex_value(self, client, app):
        response = client.post('/auth/register', data={
            'first_name': 'Invalid', 'last_name': 'Response',
            'email': 'invalid-sex@test.com', 'password': 'secret123',
            'id_number': '21-0004', 'campus': '1',
            'volunteer_type': 'student', 'sex': 'unknown',
            'college_affiliation': 'College of Computing Sciences',
        })
        assert response.status_code == 200
        with app.app_context():
            assert User.query.filter_by(email='invalid-sex@test.com').first() is None

    def test_complete_sex_accepts_prefer_not_to_say(self, client, app):
        user_id = _create_user(app, email='complete-sex@test.com',
                               role='volunteer', campus_id=1, sex=None)
        _login_as(client, user_id)
        response = client.post(
            '/auth/complete-sex', data={'sex': 'prefer_not_to_say'})
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(User, user_id).sex == 'prefer_not_to_say'

    def test_public_registration_cannot_create_privileged_role(self, client, app):
        resp = client.post('/auth/register', data={
            'first_name': 'Privilege', 'last_name': 'Attempt',
            'email': 'privilege@test.com',
            'password': 'secret123',
            'account_type': 'coordinator', 'id_number': '21-0099',
            'campus': '1', 'volunteer_type': 'student',
            'sex': 'male',
            'college_affiliation': 'College of Computing Sciences',
        })
        assert resp.status_code == 302
        with app.app_context():
            user = User.query.filter_by(email='privilege@test.com').one()
            assert user.role == 'volunteer'

    def test_csrf_rejects_post_without_token_when_enabled(self, client, app):
        app.config['WTF_CSRF_ENABLED'] = True
        resp = client.post('/auth/login', data={
            'identifier': 'nobody@test.com', 'password': 'password123',
        })
        assert resp.status_code == 400

    def test_auth_page_exposes_csrf_token_when_enabled(self, client, app):
        app.config['WTF_CSRF_ENABLED'] = True
        resp = client.get('/auth/login')
        body = resp.data.decode()
        assert re.search(r'const token = "[^"]+"', body)

    def test_register_duplicate_email(self, client, app):
        _create_user(app, email='dup@test.com')
        resp = client.post('/auth/register', data={
            'first_name': 'Dup', 'last_name': 'User',
            'email': 'dup@test.com',
            'password': 'secret123',
            'account_type': 'volunteer', 'id_number': '21-0002',
            'campus': 'Lingayen',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_get(self, client):
        resp = client.get('/auth/login')
        assert resp.status_code == 200
        assert b'name="remember"' not in resp.data
        assert b'Remember this device' not in resp.data

    @pytest.mark.parametrize('remember', ['', 'on'])
    def test_login_uses_session_only_even_with_remember_flag(self, client, app, remember):
        user_id = _create_user(app, email='session-only@test.com')
        response = client.post('/auth/login', data={
            'identifier': 'session-only@test.com', 'password': 'password123',
            'remember': remember,
        })
        assert response.status_code == 302
        assert response.location == '/volunteer_dash'
        assert client.get_cookie('remember_token') is None
        assert client.get_cookie('session').expires is None
        with client.session_transaction() as saved_session:
            assert saved_session['_user_id'] == str(user_id)
            assert saved_session['auth_version'] == 1
            assert not saved_session.permanent
        assert client.get('/volunteer_dash').status_code == 200

    def test_login_valid_redirects(self, client, app):
        _create_user(app, email='valid@test.com')
        resp = client.post('/auth/login', data={
            'identifier': 'valid@test.com', 'password': 'password123',
        })
        assert resp.status_code == 302
        assert resp.location == '/volunteer_dash'

    def test_login_invalid_shows_error(self, client):
        resp = client.post('/auth/login', data={
            'identifier': 'nobody@test.com', 'password': 'wrong',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_is_throttled_after_repeated_failures(self, client):
        for _ in range(5):
            response = client.post('/auth/login', data={
                'identifier': 'throttle@test.com', 'password': 'wrong'})
            assert response.status_code == 200
        response = client.post('/auth/login', data={
            'identifier': 'throttle@test.com', 'password': 'wrong'})
        assert response.status_code == 429

    def test_logout_requires_login(self, client):
        resp = client.post('/auth/logout', follow_redirects=True)
        assert resp.status_code == 200

    def test_password_reset_uses_expiring_single_use_token(self, client, app):
        _create_user(app, email='recover@test.com')
        response = client.post('/auth/forgot-password', data={
            'email': 'recover@test.com'}, follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            token = PasswordResetToken.query.one()
            assert token.used_at is None
            assert token.expires_at > datetime.utcnow()

    def test_expired_password_reset_token_is_rejected(self, client, app):
        user_id = _create_user(app, email='expired-reset@test.com')
        raw_token = 'expired-token'
        with app.app_context():
            db.session.add(PasswordResetToken(
                user_id=user_id, token_hash=sha256(raw_token.encode()).hexdigest(),
                expires_at=datetime.utcnow() - timedelta(minutes=1)))
            db.session.commit()
        response = client.get(f'/auth/reset-password/{raw_token}')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/auth/forgot-password')

    def test_protected_route_redirects_anon(self, client):
        resp = client.get('/volunteer_dash')
        assert resp.status_code == 302
        assert '/auth/login' in resp.location


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# C. Role-based Access
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestLoginReturnDestinations:
    def test_login_rejects_external_and_browser_normalized_targets(self, client, app):
        _create_user(app, email='redirect@test.com')
        unsafe_targets = (
            'https://example.org/phishing', 'http://localhost/volunteer_dash',
            '//example.org', '///example.org', '\\\\example.org', '/\\example.org',
            'javascript:alert(1)', 'data:text/html,unsafe', 'volunteer_dash',
            ' https://example.org', '\t//example.org', '/\n/example.org',
            '/%2fexample.org', '%2f%2fexample.org', '%2fopportunities', '/%5cexample.org',
            '/%09/example.org', '/%0d%0aLocation:https://example.org',
            '/\x00example.org', '/%7fexample.org',
        )
        for target in unsafe_targets:
            response = client.post('/auth/login', query_string={'next': target}, data={
                'identifier': 'redirect@test.com', 'password': 'password123'})
            assert response.status_code == 302
            assert response.headers['Location'] == '/volunteer_dash', repr(target)
            client.post('/auth/logout')

    def test_login_form_preserves_local_paths_queries_and_fragments(self, client, app):
        _create_user(app, email='return@test.com')
        targets = (
            '/opportunities/register/1', '/',
            '/opportunities?search=Community%20Food&campus=2#results',
            '/opportunities?search=%E6%9C%8D%E5%8A%A1',
        )
        for target in targets:
            body = client.get('/auth/login', query_string={'next': target}).get_data(as_text=True)
            action = unescape(re.search(r'<form action="([^"]+)" method="post">', body).group(1))
            response = client.post(action, data={
                'identifier': 'return@test.com', 'password': 'password123'})
            assert response.status_code == 302
            assert response.headers['Location'] == target
            if target == '/opportunities/register/1':
                review = client.get(response.headers['Location'])
                assert review.status_code == 200
                assert 'name="accept_agreement"' in review.get_data(as_text=True)
                with app.app_context():
                    assert Registration.query.count() == 0
            client.post('/auth/logout')

    @pytest.mark.parametrize('role,dashboard', [
        ('volunteer', '/volunteer_dash'), ('coordinator', '/coordinator_dash'),
        ('director', '/director_dash'), ('admin', '/admin_dash'),
    ])
    def test_unsafe_next_uses_role_dashboard(self, client, app, role, dashboard):
        _create_user(app, email='role-return@test.com', role=role, campus_id=1)
        for target in ('https://example.org', ''):
            response = client.post('/auth/login', query_string={'next': target}, data={
                'identifier': 'role-return@test.com', 'password': 'password123'})
            assert response.status_code == 302
            assert response.headers['Location'] == dashboard
            client.post('/auth/logout')

    @pytest.mark.parametrize('policy', ['terms', 'privacy'])
    @pytest.mark.parametrize('state', ['not-published', 'accepted', 'pending'])
    @pytest.mark.parametrize('target', [
        '//example.org', '/opportunities/register/1?source=return',
    ])
    def test_policy_returns_revalidate_saved_destinations(
            self, client, app, policy, state, target):
        uid = _create_user(app, email='policy-return@test.com')
        revision_model = TermsRevision if policy == 'terms' else PrivacyRevision
        acceptance_model = TermsAcceptance if policy == 'terms' else PrivacyAcknowledgement
        if state != 'not-published':
            with app.app_context():
                revision = revision_model(title='Preview policy', body='Test policy.', version='1')
                db.session.add(revision)
                db.session.flush()
                if state == 'accepted':
                    db.session.add(acceptance_model(user_id=uid, revision_id=revision.id))
                db.session.commit()
        _login_as(client, uid)
        with client.session_transaction() as saved_session:
            saved_session[f'{policy}_next'] = target
        data = {'accept_terms': 'on'} if policy == 'terms' else {'acknowledge_privacy': 'on'}
        if state == 'pending':
            response = client.post(f'/auth/{policy}', data=data)
        else:
            response = client.get(f'/auth/{policy}')
        assert response.status_code == 302
        expected = target if target.startswith('/opportunities/') else '/volunteer_dash'
        assert response.headers['Location'] == expected
        with client.session_transaction() as saved_session:
            assert f'{policy}_next' not in saved_session
        if state == 'pending':
            with app.app_context():
                assert acceptance_model.query.filter_by(user_id=uid).count() == 1

    @pytest.mark.parametrize('target', [
        '/opportunities/register/1?source=login', 'https://example.org',
    ])
    def test_login_returns_after_required_terms_and_privacy(self, client, app, target):
        uid = _create_user(app, email='policy-chain@test.com')
        with app.app_context():
            db.session.add(TermsRevision(title='Terms', body='Test terms.', version='1'))
            db.session.add(PrivacyRevision(title='Privacy', body='Test notice.', version='1'))
            db.session.commit()
        body = client.get('/auth/login', query_string={'next': target}).get_data(as_text=True)
        action = unescape(re.search(r'<form action="([^"]+)" method="post">', body).group(1))
        response = client.post(action, data={
            'identifier': 'policy-chain@test.com', 'password': 'password123'})
        assert response.headers['Location'] == '/auth/terms'
        expected = target if target.startswith('/opportunities/') else '/volunteer_dash'
        with client.session_transaction() as saved_session:
            assert saved_session['terms_next'] == expected
        # Missing consent keeps the destination pending and records no acceptance.
        assert client.post('/auth/terms', data={}).status_code == 200
        with app.app_context():
            assert TermsAcceptance.query.filter_by(user_id=uid).count() == 0
        response = client.post('/auth/terms', data={'accept_terms': 'on'})
        assert response.headers['Location'] == expected
        response = client.get(response.headers['Location'])
        assert response.headers['Location'] == '/auth/privacy'
        assert client.post('/auth/privacy', data={}).status_code == 200
        response = client.post('/auth/privacy', data={'acknowledge_privacy': 'on'})
        assert response.headers['Location'] == expected
        destination = client.get(response.headers['Location'])
        assert destination.status_code == 200
        with app.app_context():
            assert TermsAcceptance.query.filter_by(user_id=uid).count() == 1
            assert PrivacyAcknowledgement.query.filter_by(user_id=uid).count() == 1
            assert Registration.query.count() == 0

    def test_return_form_keeps_csrf_protection(self, client, app):
        _create_user(app, email='csrf-return@test.com')
        app.config['WTF_CSRF_ENABLED'] = True
        target = '/opportunities/register/1'
        body = client.get('/auth/login', query_string={'next': target}).get_data(as_text=True)
        action = unescape(re.search(r'<form action="([^"]+)" method="post">', body).group(1))
        data = {'identifier': 'csrf-return@test.com', 'password': 'password123'}
        assert client.post(action, data=data).status_code == 400
        data['csrf_token'] = re.search(r'const token = "([^"]+)"', body).group(1)
        response = client.post(action, data=data)
        assert response.status_code == 302
        assert response.headers['Location'] == target


class TestPhaseOnePublicExperience:
    def test_coordinator_target_progress_matches_workspace_status(self, client, app):
        user_id = _create_user(app, email='target-scope@test.com', role='coordinator', campus_id=1)
        with app.app_context():
            db.session.add_all([
                Event(title='Past scope check', description='Scope check',
                      date=datetime.now() - timedelta(days=3), slots=10, campus_id=1),
                Event(title='Upcoming scope check', description='Scope check',
                      date=datetime.now() + timedelta(days=3), slots=10, campus_id=1),
            ])
            db.session.commit()
        _login_as(client, user_id)
        body = client.get('/coordinator_dash').get_data(as_text=True)
        assert 'Upcoming scope check' in body
        assert 'Past scope check' not in body

    @pytest.mark.parametrize('role,path', [
        ('coordinator', '/coordinator_analytics'), ('director', '/analytics'),
    ])
    def test_invalid_analytics_date_range_shows_a_recovery_message(self, client, app, role, path):
        user_id = _create_user(app, email=f'dates-{role}@test.com', role=role, campus_id=1)
        _login_as(client, user_id)
        response = client.get(path + '?start_date=2026-10-18&end_date=2020-01-01', follow_redirects=True)
        assert response.status_code == 200
        assert 'Use valid report dates' in response.get_data(as_text=True)

    @pytest.mark.parametrize('role,path', [
        ('volunteer', '/volunteer_dash'),
        ('coordinator', '/coordinator_dash'),
        ('director', '/director_dash'),
        ('admin', '/admin_dash'),
    ])
    def test_first_dashboard_starts_its_role_guide(self, client, app, role, path):
        user_id = _create_user(app, email=f'tour-{role}@test.com', role=role, campus_id=1)
        _login_as(client, user_id)
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f'data-tour-role="{role}"' in body
        assert 'data-tour-first-use="true"' in body
        assert client.post('/guide/dismiss').status_code == 302
        assert 'data-tour-first-use="false"' in client.get(path).get_data(as_text=True)

    def test_home_shows_live_opportunities_and_institutional_summary(self, client):
        response = client.get('/')
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'Serve with purpose.' in body
        assert 'Featured opportunities' in body
        assert 'Institutional record' in body
        assert '/historical-activities' in body
        assert '/help' in body

    @pytest.mark.parametrize('start_hours,end_hours,completed', [
        pytest.param(-2, 1, False, id='ongoing'),
        pytest.param(-2, -1, True, id='ended'),
        pytest.param(-2, 0, True, id='ends-now'),
        pytest.param(1, 2, False, id='upcoming'),
        pytest.param(-1, None, True, id='legacy-past-start'),
        pytest.param(1, None, False, id='legacy-future-start'),
        pytest.param(0, None, True, id='legacy-starts-now'),
    ])
    def test_home_completed_activities_use_effective_end_time(
            self, client, app, monkeypatch, start_hours, end_hours, completed):
        now = datetime.now().replace(microsecond=0)
        with app.app_context():
            db.session.add(Event(
                title='Schedule boundary activity', description='Schedule boundary check.',
                date=now + timedelta(hours=start_hours),
                end_date=now + timedelta(hours=end_hours) if end_hours is not None else None,
                slots=10, campus_id=1))
            db.session.commit()

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls):
                return now

        monkeypatch.setattr('datetime.datetime', FrozenDatetime)
        response = client.get('/')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        stories = re.findall(r'<article class="story-card">.*?<h3>(.*?)</h3>', body, re.S)
        assert ('Schedule boundary activity' in stories) == completed
        featured = re.findall(r'<article class="featured-card">.*?<h3>(.*?)</h3>', body, re.S)
        assert not (completed and 'Schedule boundary activity' in featured)
        if not completed:
            assert not stories
            assert 'Completed activities will appear here' in body

    def test_home_completed_stories_show_latest_three_finishes(self, client, app):
        now = datetime.now()
        with app.app_context():
            for title, start_hours, end_hours in (
                ('Latest finish', -4, -0.5),
                ('Long-running activity', -240, -1),
                ('Legacy start fallback', -2, None),
                ('More recent start, earlier finish', -4, -3),
                ('Same finish, later record', -72, -1),
            ):
                db.session.add(Event(
                    title=title, description='Completion ordering check.',
                    date=now + timedelta(hours=start_hours),
                    end_date=now + timedelta(hours=end_hours) if end_hours is not None else None,
                    slots=10, campus_id=1))
            db.session.commit()
        body = client.get('/').get_data(as_text=True)
        stories = re.findall(r'<article class="story-card">.*?<h3>(.*?)</h3>', body, re.S)
        assert stories == ['Latest finish', 'Same finish, later record', 'Long-running activity']

    def test_historical_activity_directory_renders(self, client):
        response = client.get('/historical-activities')
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'Volunteer activities, CY 2020–2025' in body
        assert 'aggregate records' in body

    def test_help_guide_explains_recommendations(self, client):
        response = client.get('/help')
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'How to use the Volunteer Hub' in body
        assert 'cosine similarity' in body

    def test_help_guide_shows_the_signed_in_users_dashboard_link(self, client, app):
        user_id = _create_user(
            app, email='help-director@test.com', role='director', campus_id=1)
        _login_as(client, user_id)

        body = client.get('/help').get_data(as_text=True)

        assert 'href="/dashboard"' in body
        assert '>Dashboard</a>' in body
        assert 'Use your dashboard' in body
        assert 'Open dashboard' in body
        assert 'href="/auth/login"' not in body
        assert 'href="/auth/interests"' not in body
        assert 'Create an account' not in body
        assert 'external-volunteer option' not in body

    def test_volunteer_can_dismiss_first_use_guide(self, client, app):
        user_id = _create_user(app, email='guide@test.com')
        with app.app_context():
            db.session.get(User, user_id).sex = 'prefer_not_to_say'
            db.session.commit()
        _login_as(client, user_id)

        dashboard = client.get('/volunteer_dash').get_data(as_text=True)
        assert 'data-tour-first-use="true"' in dashboard
        assert 'first-use-tour.js' in dashboard
        assert client.post('/guide/dismiss').status_code == 302
        with app.app_context():
            assert db.session.get(User, user_id).first_use_guide_dismissed_at is not None

    def test_dashboard_guide_replays_without_resetting_first_use_state(self, client, app):
        user_id = _create_user(app, email='replay-guide@test.com', role='coordinator', campus_id=1)
        dismissed_at = datetime.utcnow()
        with app.app_context():
            db.session.get(User, user_id).first_use_guide_dismissed_at = dismissed_at
            db.session.commit()
        _login_as(client, user_id)

        body = client.get('/coordinator_dash?tour=1').get_data(as_text=True)
        assert 'data-tour-first-use="false"' in body
        assert 'data-tour-replay="true"' in body
        assert 'data-tour-id="activity-workspace"' in body
        with app.app_context():
            assert db.session.get(User, user_id).first_use_guide_dismissed_at == dismissed_at

    def test_anonymous_user_cannot_dismiss_an_account_guide(self, client):
        response = client.post('/guide/dismiss')
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

    def test_management_dashboards_render_info_tips(self, client, app):
        coordinator_id = _create_user(
            app, email='tips-coordinator@test.com', role='coordinator', campus_id=1)
        _login_as(client, coordinator_id)
        coordinator_body = client.get('/coordinator_dash').get_data(as_text=True)
        assert 'class="info-tip"' in coordinator_body
        assert 'About attendance rate' in coordinator_body

    def test_director_analytics_renders_info_tips(self, client, app):
        director_id = _create_user(app, email='tips-director@test.com', role='director', campus_id=1)
        _login_as(client, director_id)
        director_body = client.get('/analytics').get_data(as_text=True)
        assert 'class="info-tip"' in director_body
        assert 'About live activity report' in director_body

    def test_director_analytics_separates_live_and_historical_views(self, client, app):
        director_id = _create_user(
            app, email='analytics-views@test.com', role='director', campus_id=1)
        _login_as(client, director_id)

        live = client.get('/analytics?view=live').get_data(as_text=True)
        historical = client.get('/analytics?view=historical').get_data(as_text=True)
        invalid = client.get('/analytics?view=unsupported').get_data(as_text=True)

        assert 'analytics-view-switcher' in live
        assert 'Live Activity Report' in live
        assert 'Historical Activities' not in live
        assert 'Historical Activities' in historical
        assert 'Live Activity Report' not in historical
        assert 'Role demographics' not in historical
        assert 'Live Activity Report' in invalid

    def test_live_analytics_keeps_advanced_filters_out_of_the_primary_scope(self, client, app):
        director_id = _create_user(
            app, email='analytics-filters@test.com', role='director', campus_id=1)
        _login_as(client, director_id)

        default = client.get('/analytics?view=live').get_data(as_text=True)
        advanced = client.get(
            '/analytics?view=live&sex=female&campus_mode=include&campus=1'
        ).get_data(as_text=True)
        csv_href = re.search(
            r'href="([^"]*/reports/university\.csv[^"]*)"', advanced).group(1)

        assert 'Filters and Reports' in default
        assert '<details class="analytics-advanced-filters">' in default
        assert 'More Filters (Active)' not in default
        assert '<details class="analytics-advanced-filters" open>' in advanced
        assert 'More Filters (Active)' in advanced
        assert parse_qs(urlsplit(csv_href).query)['sex'] == ['female']

    def test_coordinator_analytics_uses_title_case_filter_heading(self, client, app):
        coordinator_id = _create_user(
            app, email='coordinator-filters@test.com', role='coordinator', campus_id=1)
        _login_as(client, coordinator_id)

        body = client.get('/coordinator_analytics').get_data(as_text=True)

        assert '<h2 id="filter-heading">Filters and Reports</h2>' in body

    def test_coordinator_dashboard_prioritizes_attention_before_evidence(self, client, app):
        coordinator_id = _create_user(
            app, email='dashboard-priority@test.com', role='coordinator', campus_id=1)
        _login_as(client, coordinator_id)

        body = client.get('/coordinator_dash').get_data(as_text=True)
        assert body.index('Needs Attention') < body.index('Activity Workspace')
        assert body.index('Activity Workspace') < body.index('Supporting Evidence')
        assert 'Review requests' in body
        assert 'Track attendance' in body

    def test_guide_dismissal_only_updates_the_authenticated_user(self, client, app):
        current_id = _create_user(app, email='guide-current@test.com', role='coordinator', campus_id=1)
        other_id = _create_user(app, email='guide-other@test.com', role='director', campus_id=1)
        _login_as(client, current_id)

        assert client.post('/guide/dismiss', data={'user_id': other_id}).status_code == 302
        with app.app_context():
            assert db.session.get(User, current_id).first_use_guide_dismissed_at is not None
            assert db.session.get(User, other_id).first_use_guide_dismissed_at is None

    def test_guide_dismissal_requires_csrf_and_accepts_a_valid_token(self, client, app):
        user_id = _create_user(app, email='guide-csrf@test.com', role='director')
        _login_as(client, user_id)
        app.config['WTF_CSRF_ENABLED'] = True
        assert client.post('/guide/dismiss').status_code == 400
        body = client.get('/director_dash').get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', body).group(1)
        response = client.post('/guide/dismiss', headers={
            'X-CSRFToken': token, 'Accept': 'application/json'})
        assert response.status_code == 200
        assert response.json == {'dismissed': True}


class TestRoleAccess:
    def test_volunteer_can_access_volunteer_dash(self, client, app):
        uid = _create_user(app, email='vol@test.com')
        _login_as(client, uid)
        resp = client.get('/volunteer_dash')
        assert resp.status_code == 200

    def test_volunteer_cannot_access_coordinator_dash(self, client, app):
        uid = _create_user(app, email='vol2@test.com')
        _login_as(client, uid)
        resp = client.get('/coordinator_dash', follow_redirects=True)
        assert resp.status_code == 403

    def test_coordinator_can_access_coordinator_dash(self, client, app):
        uid = _create_user(app, email='coord@test.com', role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/coordinator_dash')
        assert resp.status_code == 200

    def test_director_can_access_director_dash(self, client, app):
        uid = _create_user(app, email='dir@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/director_dash')
        assert resp.status_code == 200

    def test_director_can_access_analytics(self, client, app):
        uid = _create_user(app, email='dir2@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/analytics')
        assert resp.status_code == 200

    def test_admin_can_access_admin_dash(self, client, app):
        uid = _create_user(app, email='admin@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/admin_dash')
        assert resp.status_code == 200

    def test_unauthenticated_redirected_to_login(self, client):
        for path in ('/volunteer_dash', '/coordinator_dash', '/director_dash', '/admin_dash'):
            resp = client.get(path)
            assert resp.status_code == 302
            assert '/auth/login' in resp.location


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# D. Volunteer Features
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestVolunteerFeatures:
    def test_volunteer_dash_renders(self, client, app):
        uid = _create_user(app, email='vdash@test.com')
        _login_as(client, uid)
        resp = client.get('/volunteer_dash')
        assert resp.status_code == 200

    def test_opportunities_lists(self, client):
        resp = client.get('/opportunities')
        assert resp.status_code == 200

    def test_register_for_event(self, client, app):
        uid = _create_user(app, email='reg@test.com')
        _login_as(client, uid)
        with app.app_context():
            eid = Event.query.first().id
        resp = client.post(f'/opportunities/register/{eid}', data={'accept_agreement': 'yes'}, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            r = Registration.query.filter_by(user_id=uid).first()
            assert r is not None
            assert r.event_id == eid

    def test_home_join_links_review_agreements_before_registering(self, client, app):
        uid = _create_user(app, email='home-join@test.com')
        _login_as(client, uid)
        with app.app_context():
            event = db.session.get(Event, 1)
            event.participation_agreement_text = 'Activity participation terms.'
            event.participation_agreement_version = 'activity-1'
            event.nda_required = True
            event.nda_text = 'Keep activity materials confidential.'
            event.nda_version = 'nda-1'
            db.session.commit()
        body = client.get('/').get_data(as_text=True)
        join_links = re.findall(
            r'<a\b[^>]*href="(/opportunities/register/\d+)"[^>]*>Join Now</a>', body)
        # The homepage shortcut and dedicated details page both use agreement review.
        assert join_links.count('/opportunities/register/1') == 1
        assert 'href="/opportunities/1"' in body
        assert 'data-open-event' not in body
        assert 'href="/opportunities/register/1"' in client.get('/opportunities/1').get_data(as_text=True)
        assert not re.search(r'<form\b[^>]*action="/opportunities/register/', body)
        for link in join_links:
            response = client.get(link)
            assert response.status_code == 200
            assert 'name="accept_agreement"' in response.get_data(as_text=True)
        consent = client.get('/opportunities/register/1').get_data(as_text=True)
        assert 'Activity participation terms.' in consent
        assert 'name="accept_nda"' in consent
        with app.app_context():
            assert Registration.query.filter_by(user_id=uid).count() == 0
        response = client.post('/opportunities/register/1', data={
            'accept_agreement': 'yes', 'accept_nda': 'yes'}, follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            registration = Registration.query.filter_by(user_id=uid, event_id=1).one()
            assert registration.status == 'confirmed'
            assert registration.policy_version == 'activity-1'
            assert registration.policy_accepted_at is not None
            assert registration.nda_version == 'nda-1'
            assert registration.nda_accepted_at is not None

    @pytest.mark.parametrize('method', ['get', 'post'])
    @pytest.mark.parametrize('seconds_before_start', [-1, 0, 1])
    def test_join_enforces_start_time_boundary(
            self, client, app, monkeypatch, method, seconds_before_start):
        from app.routes import events as events_routes

        start = datetime(2030, 6, 10, 9)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls):
                return start - timedelta(seconds=seconds_before_start)

        monkeypatch.setattr(events_routes, 'datetime', FrozenDatetime)
        uid = _create_user(app, email='join-boundary@test.com')
        _login_as(client, uid)
        with app.app_context():
            db.session.get(Event, 1).date = start
            db.session.commit()
        response = getattr(client, method)(
            '/opportunities/register/1', data={'accept_agreement': 'yes'})
        if seconds_before_start > 0:
            assert response.status_code == (200 if method == 'get' else 302)
        else:
            assert response.status_code == 302
            assert response.headers['Location'].endswith('/opportunities/1')
            with client.session_transaction() as session:
                assert ('error', 'This activity has already started and cannot accept registrations.') in session['_flashes']
        with app.app_context():
            expected_count = int(seconds_before_start > 0 and method == 'post')
            assert Registration.query.filter_by(user_id=uid, event_id=1).count() == expected_count

    @pytest.mark.parametrize('cancelled', [False, True])
    def test_join_rechecks_start_after_review_without_changing_registration(
            self, client, app, cancelled):
        uid = _create_user(app, email='join-stale@test.com')
        _login_as(client, uid)
        accepted_at = datetime(2026, 1, 1)
        with app.app_context():
            if cancelled:
                db.session.add(Registration(
                    user_id=uid, event_id=1, status='cancelled',
                    policy_version='original', policy_accepted_at=accepted_at,
                    nda_version='original-nda', nda_accepted_at=accepted_at))
                db.session.commit()
            audit_count = AuditLog.query.count()
            notification_count = Notification.query.count()
        assert client.get('/opportunities/register/1').status_code == 200
        with app.app_context():
            db.session.get(Event, 1).date = datetime.now() - timedelta(seconds=1)
            db.session.commit()
        response = client.post('/opportunities/register/1',
                               data={'accept_agreement': 'yes'}, follow_redirects=True)
        assert response.status_code == 200
        assert 'already started and cannot accept registrations' in response.get_data(as_text=True)
        with app.app_context():
            registrations = Registration.query.filter_by(user_id=uid, event_id=1).all()
            assert len(registrations) == int(cancelled)
            if cancelled:
                registration = registrations[0]
                assert registration.status == 'cancelled'
                assert registration.policy_version == 'original'
                assert registration.policy_accepted_at == accepted_at
                assert registration.nda_version == 'original-nda'
                assert registration.nda_accepted_at == accepted_at
            assert AuditLog.query.count() == audit_count
            assert Notification.query.count() == notification_count

    def test_join_still_requires_agreement_nda_and_csrf(self, client, app):
        uid = _create_user(app, email='join-consent@test.com')
        _login_as(client, uid)
        with app.app_context():
            event = db.session.get(Event, 1)
            event.nda_required = True
            event.nda_text = 'Keep activity materials confidential.'
            event.nda_version = 'nda-1'
            db.session.commit()
        for data in ({}, {'accept_agreement': 'yes'}, {'accept_nda': 'yes'}):
            assert client.post('/opportunities/register/1', data=data).status_code == 400
        app.config['WTF_CSRF_ENABLED'] = True
        data = {'accept_agreement': 'yes', 'accept_nda': 'yes'}
        assert client.post('/opportunities/register/1', data=data).status_code == 400
        with app.app_context():
            assert Registration.query.filter_by(user_id=uid).count() == 0
        body = client.get('/opportunities/register/1').get_data(as_text=True)
        data['csrf_token'] = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', body).group(1)
        assert client.post('/opportunities/register/1', data=data).status_code == 302
        with app.app_context():
            assert Registration.query.filter_by(user_id=uid, event_id=1).one().status == 'confirmed'

    def test_volunteer_can_request_future_registration_cancellation(self, client, app):
        uid = _create_user(app, email='cancel@test.com', campus_id=1)
        _login_as(client, uid)
        with app.app_context():
            event = Event.query.first()
            event_id = event.id
        client.post(f'/opportunities/register/{event_id}', data={'accept_agreement': 'yes'})
        with app.app_context():
            registration = Registration.query.filter_by(
                user_id=uid, event_id=event_id).first()
            registration_id = registration.id
        response = client.post(f'/registrations/{registration_id}/cancel', data={'reason': 'Academic Conflict'})
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Registration, registration_id).status == 'confirmed'
            assert db.session.get(Registration, registration_id).cancellation_request.status == 'pending'

    def test_volunteer_cannot_cancel_another_users_registration(self, client, app):
        owner_id = _create_user(app, email='owner@test.com', campus_id=1)
        other_id = _create_user(app, email='other@test.com', campus_id=1)
        with app.app_context():
            registration = Registration(user_id=owner_id, event_id=1, status='confirmed')
            db.session.add(registration)
            db.session.commit()
            registration_id = registration.id
        _login_as(client, other_id)
        assert client.post(f'/registrations/{registration_id}/cancel').status_code == 403

    def test_dashboard_lists_registration_and_cancel_control(self, client, app):
        uid = _create_user(app, email='dashboardreg@test.com', campus_id=1)
        with app.app_context():
            db.session.add(Registration(user_id=uid, event_id=1, status='confirmed'))
            db.session.commit()
        _login_as(client, uid)
        body = client.get('/volunteer_dash').get_data(as_text=True)
        assert 'My registrations' in body
        assert '/registrations/' in body

    def test_profile_get(self, client, app):
        uid = _create_user(app, email='prof@test.com')
        _login_as(client, uid)
        resp = client.get('/profile')
        assert resp.status_code == 200

    def test_profile_post_updates(self, client, app):
        uid = _create_user(app, email='profup@test.com')
        with app.app_context():
            skills = [Skill(name='Phase 2 Skill A'), Skill(name='Phase 2 Skill B')]
            interests = [Interest(name='Phase 2 Interest A'),
                         Interest(name='Phase 2 Interest B')]
            db.session.add_all([*skills, *interests])
            db.session.commit()
            skill_ids = [str(skill.id) for skill in skills]
            interest_ids = [str(interest.id) for interest in interests]
        _login_as(client, uid)
        resp = client.post('/profile', data={
            'skills': skill_ids,
            'interests': interest_ids,
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            u = User.query.filter_by(email='profup@test.com').first()
            assert u is not None
            assert {s.name for s in u.skills} == {
                'Phase 2 Skill A', 'Phase 2 Skill B'}
            assert {i.name for i in u.interests} == {
                'Phase 2 Interest A', 'Phase 2 Interest B'}

    def test_history_shows(self, client, app):
        uid = _create_user(app, email='hist@test.com')
        _login_as(client, uid)
        resp = client.get('/profile')
        assert resp.status_code == 200


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# E. Coordinator Features
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAttendanceTiming:
    NOW = datetime(2040, 6, 10, 12)

    def _setup(self, app, client, monkeypatch, has_end=True, offset=-1):
        import app.routes.coordinator as coordinator
        now = self.NOW
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr(coordinator, 'datetime', FrozenDatetime)
        reviewer = _create_user(app, email='timing-coord@test.com', role='coordinator', campus_id=1)
        owner = _create_user(app, email='timing-vol@test.com', campus_id=1)
        with app.app_context():
            event = db.session.get(Event, 1)
            event.date = now - timedelta(hours=2) if has_end else now + timedelta(seconds=offset)
            event.end_date = now + timedelta(seconds=offset) if has_end else None
            registration = Registration(user_id=owner, event_id=1, status='confirmed')
            db.session.add(registration)
            db.session.commit()
            registration_id = registration.id
        _login_as(client, reviewer)
        return registration_id

    @pytest.mark.parametrize('has_end', [True, False])
    @pytest.mark.parametrize('offset', [-1, 0, 1])
    def test_effective_end_boundary_and_ui(self, app, client, monkeypatch, has_end, offset):
        rid = self._setup(app, client, monkeypatch, has_end, offset)
        body = client.get('/attendance?event_id=1').get_data(as_text=True)
        button = re.search(r'<button[^>]*class="[^"]*attendance-save[^>]*>.*?</button>', body).group(0)
        assert 'disabled' not in button
        assert ('Check-in Active' in body or 'Final Attendance Due' in body)
        response = client.post('/attendance', data={
            'event_id': 1, 'registration_id': rid, 'status': 'present'}, follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            registration = db.session.get(Registration, rid)
            assert registration.status == ('confirmed' if offset > 0 else 'completed')
            assert registration.certificate_eligible == (offset <= 0)
            assert Attendance.query.filter_by(registration_id=rid).count() == 1
        if offset > 0:
            assert 'Check-in saved.' in response.get_data(as_text=True)

    @pytest.mark.parametrize('status', ['absent', 'excused'])
    def test_all_status_writes_are_blocked_before_checkin(self, app, client, monkeypatch, status):
        rid = self._setup(app, client, monkeypatch, offset=3600)
        with app.app_context():
            db.session.get(Event, 1).date = self.NOW + timedelta(hours=1)
            db.session.commit()
        client.post('/attendance', data={'event_id': 1, 'registration_id': rid, 'status': status})
        with app.app_context():
            assert db.session.get(Registration, rid).status == 'confirmed'
            assert Attendance.query.filter_by(registration_id=rid).count() == 0

    def test_stale_page_rechecks_current_schedule(self, app, client, monkeypatch):
        rid = self._setup(app, client, monkeypatch)
        assert 'Check-in is not open yet.' not in client.get('/attendance?event_id=1').get_data(as_text=True)
        with app.app_context():
            db.session.get(Event, 1).date = self.NOW + timedelta(hours=1)
            db.session.get(Event, 1).end_date = self.NOW + timedelta(hours=1)
            db.session.commit()
        client.post('/attendance', data={'event_id': 1, 'registration_id': rid, 'status': 'present'})
        with app.app_context():
            assert not db.session.get(Registration, rid).certificate_eligible
            assert Attendance.query.filter_by(registration_id=rid).count() == 0

    def test_locked_existing_records_are_not_rewritten(self, app, client, monkeypatch):
        rid = self._setup(app, client, monkeypatch, offset=3600)
        with app.app_context():
            db.session.get(Event, 1).date = self.NOW + timedelta(hours=1)
            registration = db.session.get(Registration, rid)
            registration.status = 'completed'
            db.session.add(Attendance(registration_id=rid, event_id=1,
                                      user_id=registration.user_id, status='present'))
            db.session.commit()
        client.post('/attendance', data={'event_id': 1, 'registration_id': rid, 'status': 'absent'})
        with app.app_context():
            assert db.session.get(Registration, rid).status == 'completed'
            assert Attendance.query.filter_by(registration_id=rid).one().status == 'present'

    def test_open_attendance_requires_csrf(self, app, client, monkeypatch):
        rid = self._setup(app, client, monkeypatch)
        app.config['WTF_CSRF_ENABLED'] = True
        body = client.get('/attendance?event_id=1').get_data(as_text=True)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', body).group(1)
        data = {'event_id': 1, 'registration_id': rid, 'status': 'present'}
        assert client.post('/attendance', data=data).status_code == 400
        with app.app_context():
            assert Attendance.query.filter_by(registration_id=rid).count() == 0
        data['csrf_token'] = token
        assert client.post('/attendance', data=data).status_code == 302
        with app.app_context():
            assert db.session.get(Registration, rid).certificate_eligible

    def test_external_checkin_does_not_complete_participation(self, app, client, monkeypatch):
        rid = self._setup(app, client, monkeypatch, offset=3600)
        with app.app_context():
            external = ExternalParticipant(id_number='QA-TIMING-EXTERNAL')
            db.session.add(external)
            db.session.flush()
            registration = db.session.get(Registration, rid)
            registration.user_id = None
            registration.external_participant_id = external.id
            db.session.commit()
        client.post('/attendance', data={'event_id': 1, 'registration_id': rid, 'status': 'present'})
        with app.app_context():
            assert db.session.get(Registration, rid).status == 'confirmed'
            assert not db.session.get(Registration, rid).certificate_eligible
            assert Attendance.query.filter_by(registration_id=rid).one().status == 'present'

    def test_blank_attendance_status_leaves_a_registration_unmarked(self, app, client, monkeypatch):
        rid = self._setup(app, client, monkeypatch)

        response = client.post('/attendance', data={
            'event_id': 1, 'registration_id': rid, 'status': ''})

        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Registration, rid).status == 'confirmed'
            assert Attendance.query.filter_by(registration_id=rid).count() == 0

    def test_attendance_picker_lists_today_then_next_three_and_keeps_past_events(self, app, client, monkeypatch):
        import app.routes.coordinator as coordinator

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return TestAttendanceTiming.NOW

        monkeypatch.setattr(coordinator, 'datetime', FrozenDatetime)
        coordinator_id = _create_user(
            app, email='attendance-picker@test.com', role='coordinator', campus_id=1)
        with app.app_context():
            db.session.add_all([
                Event(title='Today morning', description='Today',
                      date=self.NOW.replace(hour=8), slots=10, campus_id=1),
                Event(title='Today afternoon', description='Today',
                      date=self.NOW.replace(hour=16), slots=10, campus_id=1),
                Event(title='Next one', description='Future',
                      date=self.NOW + timedelta(days=1), slots=10, campus_id=1),
                Event(title='Next two', description='Future',
                      date=self.NOW + timedelta(days=2), slots=10, campus_id=1),
                Event(title='Next three', description='Future',
                      date=self.NOW + timedelta(days=3), slots=10, campus_id=1),
                Event(title='Not in quick picker', description='Future',
                      date=self.NOW + timedelta(days=4), slots=10, campus_id=1),
                Event(title='Past review activity', description='Past',
                      date=self.NOW - timedelta(days=1), slots=10, campus_id=1),
            ])
            db.session.commit()
        _login_as(client, coordinator_id)

        body = client.get('/attendance').get_data(as_text=True)
        picker = re.search(
            r'<nav class="attendance-picker__list"[^>]*>(.*?)</nav>', body, re.S).group(1)
        expected = ['Today morning', 'Today afternoon', 'Next one', 'Next two', 'Next three']

        assert [picker.index(title) for title in expected] == sorted(
            picker.index(title) for title in expected)
        assert 'Not in quick picker' not in picker
        assert 'Past review activity' not in picker
        assert 'Past review activity' in body
        assert 'Check-in Opens' in picker

    @pytest.mark.parametrize('seconds_before_start, allowed', [(1801, False), (1800, True), (1799, True)])
    def test_early_checkin_boundary_and_finalization(self, app, client, monkeypatch, seconds_before_start, allowed):
        rid = self._setup(app, client, monkeypatch, offset=7200)
        with app.app_context():
            db.session.get(Event, 1).date = self.NOW + timedelta(seconds=seconds_before_start)
            db.session.commit()
        body = client.get('/attendance?event_id=1').get_data(as_text=True)
        button = re.search(r'<button[^>]*>Save Check-in</button>', body).group(0)
        assert ('disabled' not in button) == allowed
        data = {'event_id': 1, 'registration_id': rid, 'status': 'present'}
        client.post('/attendance', data=data)
        with app.app_context():
            registration = db.session.get(Registration, rid)
            assert registration.status == 'confirmed'
            assert not registration.certificate_eligible
            assert Attendance.query.filter_by(registration_id=rid).count() == int(allowed)
            event = db.session.get(Event, 1)
            event.date = self.NOW - timedelta(hours=2)
            event.end_date = self.NOW
            db.session.commit()
        client.post('/attendance', data=data)
        with app.app_context():
            assert db.session.get(Registration, rid).certificate_eligible
            assert Attendance.query.filter_by(registration_id=rid).count() == 1


class TestCancellationReview:
    def _request(self, app, client, reviewer_role='coordinator', reviewer_campus=1):
        owner = _create_user(app, email='review-owner@test.com', campus_id=1)
        reviewer = _create_user(app, email='reviewer@test.com', role=reviewer_role,
                                campus_id=reviewer_campus)
        with app.app_context():
            registration = Registration(user_id=owner, event_id=1, status='confirmed')
            db.session.add(registration)
            db.session.flush()
            request = CancellationRequest(registration_id=registration.id,
                                          reason='Other', details='Test-only request')
            db.session.add(request)
            db.session.commit()
            request_id, registration_id = request.id, registration.id
        _login_as(client, reviewer)
        return owner, reviewer, request_id, registration_id

    @pytest.mark.parametrize('decision, expected', [('approved', 'cancelled'), ('rejected', 'confirmed')])
    def test_decision_retains_csrf_audit_notification_and_finality(self, app, client, decision, expected):
        owner, reviewer, request_id, registration_id = self._request(app, client)
        app.config['WTF_CSRF_ENABLED'] = True
        body = client.get('/coordinator/cancellation-requests').get_data(as_text=True)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', body).group(1)
        data = {'request_id': request_id, 'decision': decision, 'review_note': 'Reviewed safely'}
        assert client.post('/coordinator/cancellation-requests', data=data).status_code == 400
        with app.app_context():
            assert db.session.get(CancellationRequest, request_id).status == 'pending'
        data['csrf_token'] = token
        response = client.post('/coordinator/cancellation-requests', data=data, follow_redirects=True)
        assert response.status_code == 200
        assert f'Cancellation request {decision}.' in response.get_data(as_text=True)
        with app.app_context():
            request = db.session.get(CancellationRequest, request_id)
            assert request.status == decision and request.reviewed_by_id == reviewer
            assert request.reviewed_at is not None and request.review_note == 'Reviewed safely'
            assert db.session.get(Registration, registration_id).status == expected
            assert AuditLog.query.filter_by(action=f'cancellation_{decision}').count() == 1
            assert Notification.query.filter_by(user_id=owner, notification_type=f'cancellation_{decision}').count() == 1
        data['decision'] = 'rejected' if decision == 'approved' else 'approved'
        client.post('/coordinator/cancellation-requests', data=data)
        with app.app_context():
            assert db.session.get(CancellationRequest, request_id).status == decision
            assert db.session.get(Registration, registration_id).status == expected
            assert AuditLog.query.filter_by(action=f'cancellation_{decision}').count() == 1
            assert Notification.query.filter_by(user_id=owner, notification_type=f'cancellation_{decision}').count() == 1

    @pytest.mark.parametrize('role, campus', [('coordinator', 2), ('volunteer', 1)])
    def test_decision_cannot_cross_role_or_campus(self, app, client, role, campus):
        _, _, request_id, registration_id = self._request(app, client, role, campus)
        assert client.post('/coordinator/cancellation-requests', data={
            'request_id': request_id, 'decision': 'approved'}).status_code == 403
        with app.app_context():
            assert db.session.get(CancellationRequest, request_id).status == 'pending'
            assert db.session.get(Registration, registration_id).status == 'confirmed'


class TestCoordinatorFeatures:
    def test_coordinator_dash_renders(self, client, app):
        uid = _create_user(app, email='cdash@test.com', role='coordinator', campus_id=1)
        with app.app_context():
            event_id = Event.query.filter_by(campus_id=1).first().id
        _login_as(client, uid)
        resp = client.get('/coordinator_dash')
        assert resp.status_code == 200
        assert f'/attendance?event_id={event_id}' in resp.get_data(as_text=True)
        assert client.get(f'/attendance?event_id={event_id}').status_code == 200

    def test_create_activity_get(self, client, app):
        uid = _create_user(app, email='create1@test.com', role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/create_activity')
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'aria-label="Assigned campus"' in body
        assert 'Lingayen' in body
        assert 'name="campus_id"' not in body

    def test_create_activity_post(self, client, app):
        uid = _create_user(app, email='create2@test.com', role='coordinator', campus_id=2)
        _login_as(client, uid)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        resp = client.post('/create_activity', data={
            'title': 'Test Event',
            'description': 'A test event',
            'date': tomorrow,
            'location': 'Test Location',
            'required_skills': 'Teaching',
            'slots': 10,
            'campus_id': 2,
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            e = Event.query.filter_by(title='Test Event').first()
            assert e is not None
            assert e.campus_id == 2

    def test_attendance_renders(self, client, app):
        uid = _create_user(app, email='attend@test.com', role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/attendance')
        assert resp.status_code == 200
        assert 'registered</span>' in resp.get_data(as_text=True)

    def test_deactivated_user_can_request_reactivation(self, client, app):
        user_id = _create_user(app, email='appeal@test.com')
        admin_id = _create_user(app, email='appeal-admin@test.com', role='admin')
        with app.app_context():
            user = db.session.get(User, user_id)
            user.is_active = False
            user.deactivated_at = datetime.utcnow()
            db.session.commit()
        login = client.post('/auth/login', data={
            'identifier': 'appeal@test.com', 'password': 'password123'})
        assert login.status_code == 200
        assert b'Account deactivated' in login.data
        requested = client.post('/auth/request-reactivation', follow_redirects=True)
        assert requested.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.reactivation_requested_at is not None
            assert Notification.query.filter_by(
                user_id=admin_id, notification_type='reactivation_request').count() == 1

    def test_coordinator_deletes_own_event_and_notifies_volunteer(self, client, app):
        coordinator_id = _create_user(
            app, email='remove-coord@test.com', role='coordinator', campus_id=1)
        volunteer_id = _create_user(app, email='remove-vol@test.com', campus_id=1)
        with app.app_context():
            event = Event.query.filter_by(campus_id=1).first()
            event_id = event.id
            db.session.add(Registration(
                user_id=volunteer_id, event_id=event_id, status='confirmed'))
            db.session.commit()
        _login_as(client, coordinator_id)
        response = client.post(f'/coordinator/events/{event_id}/delete')
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Event, event_id) is None
            assert Registration.query.filter_by(event_id=event_id).count() == 0
            assert Notification.query.filter_by(
                user_id=volunteer_id, notification_type='event_cancelled').count() == 1

    def test_coordinator_cannot_delete_other_campus_event(self, client, app):
        coordinator_id = _create_user(
            app, email='wrong-campus@test.com', role='coordinator', campus_id=1)
        with app.app_context():
            event_id = Event.query.filter_by(campus_id=2).first().id
        _login_as(client, coordinator_id)
        assert client.post(f'/coordinator/events/{event_id}/delete').status_code == 403

    def test_private_milestone_download_is_campus_scoped(self, client, app):
        coordinator_id = _create_user(
            app, email='milestone-scope@test.com', role='coordinator', campus_id=1)
        with app.app_context():
            event = Event.query.filter_by(campus_id=2).first()
            milestone = Milestone(event_id=event.id, filename='proof.pdf',
                                  upload_path='milestones/proof.pdf')
            db.session.add(milestone)
            db.session.commit()
            milestone_id = milestone.id
        _login_as(client, coordinator_id)
        assert client.get(f'/milestones/{milestone_id}/download').status_code == 403


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# F. Director Features
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestDirectorFeatures:
    def test_director_dash_renders(self, client, app):
        uid = _create_user(app, email='ddash@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/director_dash')
        assert resp.status_code == 200

    def test_analytics_renders(self, client, app):
        uid = _create_user(app, email='anl@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/analytics')
        assert resp.status_code == 200

    def test_kpis_have_expected_keys(self, app):
        from app.recommendation.analytics import AnalyticsAggregator
        with app.app_context():
            kpis = AnalyticsAggregator.kpi_summary()
            for key in ('total_active_volunteers', 'retention_rate'):
                assert key in kpis, f'KPI key {key} missing'


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# G. Admin Features
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAdminFeatures:
    def test_admin_dash_renders(self, client, app):
        uid = _create_user(app, email='adm1@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/admin_dash')
        assert resp.status_code == 200

    def test_admin_deactivate_and_reactivate_user(self, client, app):
        _create_user(app, email='target@test.com', name='Target')
        admin_uid = _create_user(app, email='adm2@test.com', role='admin')
        _login_as(client, admin_uid)
        with app.app_context():
            target = User.query.filter_by(email='target@test.com').first()
            target_id = target.id
            assert target.is_active is True
        resp = client.post(f'/admin/users/deactivate/{target_id}', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            target = db.session.get(User, target_id)
            assert target.is_active is False
        resp2 = client.post(f'/admin/users/{target_id}/reactivate',
                            follow_redirects=True)
        assert resp2.status_code == 200
        with app.app_context():
            target = db.session.get(User, target_id)
            assert target.is_active is True

    def test_admin_category_removal_moves_events_to_general(self, client, app):
        admin_uid = _create_user(app, email='category-admin@test.com', role='admin')
        _login_as(client, admin_uid)
        with app.app_context():
            from app.models.event import ActivityCategory
            category = ActivityCategory(name='Temporary Category')
            db.session.add(category)
            event = Event.query.first()
            event.category = category.name
            db.session.commit()
            category_id = category.id
            event_id = event.id
        response = client.post(f'/admin/categories/{category_id}/delete')
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Event, event_id).category == 'General'

    def test_expired_deactivated_user_can_be_deleted(self, client, app):
        admin_uid = _create_user(app, email='delete-admin@test.com', role='admin')
        target_uid = _create_user(app, email='expired-target@test.com')
        _login_as(client, admin_uid)
        with app.app_context():
            target = db.session.get(User, target_uid)
            target.is_active = False
            target.deactivated_at = datetime.utcnow() - timedelta(days=30)
            db.session.commit()
        response = client.post(f'/admin/users/{target_uid}/delete')
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(User, target_uid) is None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# H. Recommendation Engine
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestRecommendationEngine:
    def test_cosine_similarity_for_binary_terms(self):
        assert _cosine_similarity({'python', 'teaching'},
                                  {'python', 'teaching'}) == pytest.approx(1.0)
        assert _cosine_similarity({'python', 'teaching'},
                                  {'python', 'health'}) == pytest.approx(0.5)
        assert _cosine_similarity({'python'}, {'health'}) == 0.0
        assert _cosine_similarity(set(), {'python'}) == 0.0
        assert _cosine_similarity(set(), set()) == 0.0

    def _make_user_with_terms(self, email, skills, interests):
        """Create a volunteer user with skills/interests attached (3NF)."""
        user = User(name=email.split('@')[0], email=email)
        user.set_password('pw')
        db.session.add(user)
        db.session.flush()
        for name in skills:
            sk = Skill.query.filter_by(name=name).first() or Skill(name=name)
            db.session.add(sk)
            user.skills.append(sk)
        for name in interests:
            it = Interest.query.filter_by(name=name).first() or Interest(name=name)
            db.session.add(it)
            user.interests.append(it)
        profile = VolunteerProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
        return profile

    def test_returns_recommendations_for_profile(self, app):
        with app.app_context():
            profile = self._make_user_with_terms(
                'rec@test.com', ['Teaching', 'Python', 'Communication'], ['Education'])
            events = Event.query.all()
            recs = get_recommendations(profile, events)
            assert len(recs) > 0
            for r in recs:
                assert 'event' in r
                assert 'score' in r

    def test_scores_between_zero_and_one(self, app):
        with app.app_context():
            profile = self._make_user_with_terms(
                'score@test.com', ['Teaching', 'Communication'], ['Education'])
            events = Event.query.all()
            recs = get_recommendations(profile, events, top_n=len(events))
            assert len(recs) > 0
            for r in recs:
                assert 0.0 <= r['score'] <= 1.0, f'Score {r["score"]} out of range'

    def test_zero_slots_lower_score(self, app):
        with app.app_context():
            full_event = Event(title='Full Event', description='No slots available',
                               date=datetime.now() + timedelta(days=10),
                               required_skills='Teaching', slots=0, campus_id=1)
            avail_event = Event(title='Avail Event', description='Has slots',
                                date=datetime.now() + timedelta(days=10),
                                required_skills='Teaching', slots=20, campus_id=1)
            db.session.add_all([full_event, avail_event])
            db.session.commit()
            profile = self._make_user_with_terms(
                'slot@test.com', ['Teaching'], ['Education'])
            all_events = [full_event, avail_event]
            recs = get_recommendations(profile, all_events, top_n=2)
            scores = {r['event'].title: r['score'] for r in recs}
            assert scores.get('Avail Event', 0) >= scores.get('Full Event', 1), \
                'Event with slots should score >= event with zero slots'

    def test_upcoming_scores_higher_than_past(self, app):
        with app.app_context():
            future = datetime.now() + timedelta(days=30)
            past = datetime.now() - timedelta(days=30)
            future_event = Event(title='Future Event', description='In the future',
                                 date=future, required_skills='Teaching',
                                 slots=20, campus_id=1)
            past_event = Event(title='Past Event', description='Already happened',
                               date=past, required_skills='Teaching',
                               slots=20, campus_id=1)
            db.session.add_all([future_event, past_event])
            db.session.commit()
            profile = self._make_user_with_terms(
                'time@test.com', ['Teaching'], ['Education'])
            all_events = [future_event, past_event]
            recs = get_recommendations(profile, all_events, top_n=2)
            scores = {r['event'].title: r['score'] for r in recs}
            assert scores.get('Future Event', 0) >= scores.get('Past Event', 1), \
                'Future event should score higher than past event'

    def test_cold_start_returns_upcoming_events(self, app):
        with app.app_context():
            past = Event(title='Past CS', description='past',
                         date=datetime.now() - timedelta(days=1),
                         required_skills='Teaching', slots=10, campus_id=1)
            future = Event(title='Future CS', description='future',
                           date=datetime.now() + timedelta(days=2),
                           required_skills='Teaching', slots=10, campus_id=1)
            db.session.add_all([past, future])
            db.session.commit()
            recs = get_recommendations(None, top_n=5)
            titles = [r['event'].title for r in recs]
            assert 'Future CS' in titles
            assert 'Past CS' not in titles
            assert all(r['score'] == 0 for r in recs)

    def test_cold_start_prefers_popular_event(self, app):
        with app.app_context():
            popular = Event(title='Popular Event', description='many regs',
                            date=datetime.now() + timedelta(days=5),
                            required_skills='Teaching', slots=10, campus_id=1)
            quiet = Event(title='Quiet Event', description='no regs',
                          date=datetime.now() + timedelta(days=1),
                          required_skills='Teaching', slots=10, campus_id=1)
            db.session.add_all([popular, quiet])
            db.session.flush()
            from app.models.event import Registration
            for i in range(3):
                u = User(name=f'Registrant{i}', email=f'regpop{i}@test.com')
                u.set_password('pw')
                db.session.add(u)
                db.session.flush()
                db.session.add(Registration(user_id=u.id, event_id=popular.id,
                                            status='confirmed'))
            db.session.commit()
            recs = get_recommendations(None, top_n=2)
            titles = [r['event'].title for r in recs]
            assert titles.index('Popular Event') < titles.index('Quiet Event'), \
                'Popular event should rank above quiet event'

    def test_cold_start_prefers_user_campus(self, app):
        with app.app_context():
            campus2 = Event(title='Campus Two Event', description='campus 2',
                            date=datetime.now() + timedelta(days=5),
                            required_skills='Teaching', slots=10, campus_id=2)
            campus1 = Event(title='Campus One Event', description='campus 1',
                            date=datetime.now() + timedelta(days=3),
                            required_skills='Teaching', slots=10, campus_id=1)
            db.session.add_all([campus2, campus1])
            db.session.commit()
            recs = get_recommendations(None, top_n=5, campus_id=1)
            titles = [r['event'].title for r in recs]
            assert 'Campus One Event' in titles
            assert 'Campus Two Event' not in titles

    def test_bootstrap_seeds_skills_and_interests(self, app):
        with app.app_context():
            event = Event(title='Bootstrap Event', description='seed me',
                          date=datetime.now() + timedelta(days=5),
                          required_skills='Teaching, Python', slots=10,
                          campus_id=1, category='Education')
            db.session.add(event)
            db.session.commit()
            user = User(name='Boot', email='boot@test.com')
            user.set_password('pw')
            db.session.add(user)
            db.session.commit()
            bootstrap_from_event(user, event)
            assert {s.name for s in user.skills} == {'Teaching', 'Python'}
            assert {i.name for i in user.interests} == {'Education'}

    def test_bootstrap_noop_when_user_has_terms(self, app):
        with app.app_context():
            event = Event(title='Bootstrap Noop', description='no change',
                          date=datetime.now() + timedelta(days=5),
                          required_skills='Teaching', slots=10,
                          campus_id=1, category='Education')
            db.session.add(event)
            db.session.commit()
            profile = self._make_user_with_terms(
                'bootnoop@test.com', ['Communication'], ['Health'])
            u = db.session.get(User, profile.user_id)
            bootstrap_from_event(u, event)
            assert {s.name for s in u.skills} == {'Communication'}
            assert {i.name for i in u.interests} == {'Health'}

    def test_normalize_terms_collapses_variants(self):
        from app.recommendation.engine import normalize_terms
        assert normalize_terms([' IT ', 'Cs', 'Teaching']) == {
            'it/computer skills', 'computer skills', 'teaching'}

    def test_synonym_matches_variant_skill(self, app):
        # 'IT' should match an event whose skill is 'IT/Computer Skills'.
        with app.app_context():
            profile = self._make_user_with_terms(
                'synmatch@test.com', ['IT'], ['Technology'])
            event = Event(title='Syn Event', description='x',
                          date=datetime.now() + timedelta(days=5),
                          required_skills='IT/Computer Skills', slots=10,
                          campus_id=1, category='Technology')
            db.session.add(event)
            db.session.commit()
            recs = get_recommendations(profile, [event], top_n=1)
            assert recs[0]['score'] == pytest.approx(1.0)

    def test_participation_history_weights_category(self, app):
        with app.app_context():
            profile = self._make_user_with_terms(
                'histw@test.com', ['Teaching', 'Communication'], ['Education'])
            user = db.session.get(User, profile.user_id)
            # History event the volunteer previously joined (excluded later).
            hist = Event(title='History Ev', description='x',
                         date=datetime.now() - timedelta(days=10),
                         required_skills='Teaching, Communication', slots=10,
                         campus_id=1, category='Health & Wellness')
            db.session.add(hist)
            db.session.commit()
            db.session.add(Registration(
                user_id=user.id, event_id=hist.id, status='completed'))
            # Two candidate events with identical base similarity.
            ev_health = Event(title='Health Cand', description='x',
                              date=datetime.now() + timedelta(days=5),
                              required_skills='Teaching, Communication', slots=10,
                              campus_id=1, category='Health & Wellness')
            ev_sport = Event(title='Sport Cand', description='x',
                             date=datetime.now() + timedelta(days=6),
                             required_skills='Teaching, Communication', slots=10,
                             campus_id=1, category='Sports & Recreation')
            db.session.add_all([ev_health, ev_sport])
            db.session.commit()
            recs = get_recommendations(
                profile, [ev_health, ev_sport], top_n=5)
            scores = {r['event'].title: r['score'] for r in recs}
            assert scores['Health Cand'] > scores['Sport Cand']

    def test_recommendations_deterministic(self, app):
        with app.app_context():
            profile = self._make_user_with_terms(
                'determ@test.com', ['Teaching', 'Communication'], ['Education'])
            event = Event(title='Det Event', description='x',
                          date=datetime.now() + timedelta(days=5),
                          required_skills='Teaching', slots=10,
                          campus_id=1, category='Education')
            db.session.add(event)
            db.session.commit()
            first = get_recommendations(profile, [event], top_n=5)
            second = get_recommendations(profile, [event], top_n=5)
            assert [r['event'].id for r in first] == [r['event'].id for r in second]
            assert [r['score'] for r in first] == [r['score'] for r in second]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# N. In-App Notifications (Phase 15)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestNotifications:
    def test_list_requires_login(self, client):
        resp = client.get('/notifications')
        assert resp.status_code in (302, 401)

    def test_notification_visible_to_owner(self, app, client):
        uid = _create_user(app, email='volA@test.com', role='volunteer', name='VolA')
        with app.app_context():
            from app.models.notification import Notification
            db.session.add(Notification(user_id=uid, title='Hi Vol', message='m'))
            db.session.commit()
        _login_as(client, uid)
        resp = client.get('/notifications')
        assert resp.status_code == 200
        assert b'Hi Vol' in resp.data

    def test_notification_hidden_from_other_user(self, app, client):
        uid = _create_user(app, email='volA@test.com', role='volunteer', name='VolA')
        cid = _create_user(app, email='coordA@test.com', role='coordinator',
                           campus_id=1, name='CoordA')
        with app.app_context():
            from app.models.notification import Notification
            db.session.add(Notification(user_id=uid, title='Hi Vol', message='m'))
            db.session.commit()
        _login_as(client, cid)
        resp = client.get('/notifications')
        assert resp.status_code == 200
        assert b'Hi Vol' not in resp.data

    def test_mark_as_read(self, app, client):
        uid = _create_user(app, email='volB@test.com', role='volunteer', name='VolB')
        with app.app_context():
            from app.models.notification import Notification
            n = Notification(user_id=uid, title='T', message='m')
            db.session.add(n)
            db.session.commit()
            nid = n.id
        _login_as(client, uid)
        resp = client.post(f'/notifications/{nid}/read', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Notification, nid).is_read is True

    def test_mark_all_read(self, app, client):
        uid = _create_user(app, email='volE@test.com', role='volunteer', name='VolE')
        with app.app_context():
            from app.models.notification import Notification
            db.session.add(Notification(user_id=uid, title='A', message='m'))
            db.session.add(Notification(user_id=uid, title='B', message='m'))
            db.session.commit()
        _login_as(client, uid)
        resp = client.post('/notifications/read-all', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert Notification.query.filter_by(
                user_id=uid, is_read=False).count() == 0

    def test_cross_user_mark_read_denied(self, app, client):
        uid = _create_user(app, email='volC@test.com', role='volunteer', name='VolC')
        oid = _create_user(app, email='other@test.com', role='volunteer', name='Other')
        with app.app_context():
            from app.models.notification import Notification
            n = Notification(user_id=uid, title='Secret', message='m')
            db.session.add(n)
            db.session.commit()
            nid = n.id
        _login_as(client, oid)
        resp = client.post(f'/notifications/{nid}/read', follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            # Ownership enforced: the other user cannot mark it read.
            assert db.session.get(Notification, nid).is_read is False

    def test_registration_notifies_campus_coordinator(self, app, client):
        vid = _create_user(app, email='volD@test.com', role='volunteer',
                           campus_id=1, name='VolD')
        cid = _create_user(app, email='coordD@test.com', role='coordinator',
                           campus_id=1, name='CoordD')
        _login_as(client, vid)
        # Event id 1 (Youth Coding Mentor) has campus_id=1.
        resp = client.post('/opportunities/register/1',
                           data={'accept_agreement': 'yes'},
                           follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            from app.models.notification import Notification
            notes = Notification.query.filter_by(user_id=cid).all()
            assert len(notes) >= 1
            assert any('New registration' in n.title for n in notes)



# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# I. Search, Filter & Pagination
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestSearchFilterPagination:

    @pytest.mark.parametrize('signed_in', [False, True])
    @pytest.mark.parametrize('mode', ['include', 'exclude'])
    def test_multiple_campuses_for_guests_and_volunteers(self, client, app, signed_in, mode):
        if signed_in:
            _login_as(client, _create_user(app, email='multi-campus@test.com', campus_id=1))
        response = client.get('/opportunities', query_string={
            'campus': ['1', '2'], 'campus_mode': mode})
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        titles = set(re.findall(r'<h2><a[^>]+>(.*?)</a></h2>', body))
        included = {'Youth Coding Mentor', 'Green Campus Initiative', 'Community Food Drive',
                    'Rural Literacy Program', 'Coastal Cleanup Drive'}
        excluded = {'Disaster Response Training', 'Community IT Support Workshop',
                    'Community Wellness Fair', 'Sustainable Farming Demo'}
        assert titles == (included if mode == 'include' else excluded)
        assert 'name="campus" value="1" checked' in body
        assert 'name="campus" value="2" checked' in body
        assert f'value="{mode}" selected' in body
        assert 'method="get"' in body

    @pytest.mark.parametrize('mode', ['include', 'exclude'])
    def test_no_campus_selection_means_all(self, client, mode):
        response = client.get('/opportunities', query_string={
            'campus': ['', ' '], 'campus_mode': mode})
        assert response.status_code == 200
        assert 'Showing 1–9 of 9 opportunities' in response.get_data(as_text=True)

    def test_campuses_are_alphabetical_and_duplicates_are_one_choice(self, client):
        body = client.get('/opportunities?campus=1&campus=1').get_data(as_text=True)
        names = re.findall(r'name="campus" value="\d+"[^>]*>\s*<span>(.*?)</span>', body)
        assert len(names) == 9
        assert names == sorted(names, key=str.casefold)
        assert 'Showing 1–4 of 4 opportunities' in body
        assert body.count('name="campus" value="1" checked') == 1
        assert 'Campuses: 1 selected' in body

    def test_excluding_all_campuses_shows_empty_results(self, client):
        body = client.get('/opportunities', query_string={
            'campus': [str(value) for value in range(1, 10)],
            'campus_mode': 'exclude',
        }).get_data(as_text=True)
        assert '0 opportunities' in body
        assert 'No opportunities match these filters.' in body

    def test_excluding_named_campuses_keeps_unassigned_activities(self, client, app):
        with app.app_context():
            db.session.add(Event(title='Unassigned activity', description='No campus.',
                                 date=datetime.now() + timedelta(days=2), slots=10))
            db.session.commit()
        for mode in ('include', 'exclude'):
            body = client.get('/opportunities', query_string={
                'campus': ['1', '2'], 'campus_mode': mode}).get_data(as_text=True)
            assert ('>Unassigned activity</a></h2>' in body) == (mode == 'exclude')

    @pytest.mark.parametrize('invalid', ['oops', '999999', '-1', '0', '9' * 5000])
    def test_invalid_campuses_do_not_broaden_results(self, client, invalid):
        response = client.get('/opportunities', query_string={'campus': ['1', invalid]})
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert 'Some campus choices are unavailable.' in body
        assert '0 opportunities' in body
        assert 'name="campus" value="1" checked' in body

    def test_invalid_mode_shows_recoverable_error(self, client):
        response = client.get('/opportunities?campus=1&campus_mode=invalid')
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert 'Choose whether to show only or exclude' in body
        assert 'name="campus" value="1" checked' in body
        assert '0 opportunities' in body

    @pytest.mark.parametrize('mode', ['include', 'exclude'])
    def test_multi_campus_pagination_preserves_every_filter(self, client, app, mode):
        selected = ['1', '2'] if mode == 'include' else ['3', '4']
        with app.app_context():
            for index in range(13):
                db.session.add(Event(
                    title=f'Filter paging {index:02}', description='Paging check.',
                    date=datetime.now() + timedelta(days=100 + index),
                    slots=10, campus_id=1 if index % 2 else 2, category='Environment'))
            db.session.add(Event(
                title='Filter paging outside selected campuses', description='Must be omitted.',
                date=datetime.now() + timedelta(days=80), slots=10,
                campus_id=3, category='Environment'))
            db.session.commit()
        filters = {'campus': selected, 'campus_mode': mode,
                   'category': 'Environment', 'search': 'Filter paging'}
        response = client.get('/opportunities', query_string=filters)
        body = response.get_data(as_text=True)
        assert 'Showing 1–9 of 13 opportunities' in body
        assert 'outside selected campuses' not in body
        next_url = unescape(re.search(r'href="([^"]+)"\s*>Next</a>', body).group(1))
        query = parse_qs(urlsplit(next_url).query)
        assert query == {**{key: value if isinstance(value, list) else [value]
                            for key, value in filters.items()}, 'page': ['2']}
        second_page = client.get(next_url).get_data(as_text=True)
        first_titles = re.findall(r'<h2><a[^>]+>(.*?)</a></h2>', body)
        second_titles = re.findall(r'<h2><a[^>]+>(.*?)</a></h2>', second_page)
        assert len(first_titles) == 9
        assert len(second_titles) == 4
        assert not set(first_titles) & set(second_titles)
        previous_url = unescape(re.search(r'href="([^"]+)"\s*>Previous</a>', second_page).group(1))
        assert parse_qs(urlsplit(previous_url).query) == {**query, 'page': ['1']}
        for campus_id in selected:
            assert f'name="campus" value="{campus_id}" checked' in second_page

    def test_empty_campus_catalog_keeps_search_available(self, client, app):
        with app.app_context():
            Campus.query.delete()
            db.session.commit()
        response = client.get('/opportunities?search=literacy')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'No campuses are available to filter.' in body
        assert '>Rural Literacy Program</a></h2>' in body

    def test_filter_by_campus(self, client, app):
        uid = _create_user(app, email='campusfilt@test.com')
        _login_as(client, uid)
        resp = client.get('/opportunities?campus=1')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body
        assert 'Sustainable Farming Demo' not in body

    def test_filter_by_category(self, client, app):
        uid = _create_user(app, email='catfilt@test.com')
        _login_as(client, uid)
        resp = client.get('/opportunities?category=Environment')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Green Campus Initiative' in body
        assert 'Youth Coding Mentor' not in body

    def test_search_by_keyword(self, client, app):
        uid = _create_user(app, email='searchfilt@test.com')
        _login_as(client, uid)
        resp = client.get('/opportunities?search=literacy')
        assert resp.status_code == 200
        assert 'Rural Literacy Program' in resp.data.decode()

    def test_pagination_exists(self, client, app):
        uid = _create_user(app, email='pagetest@test.com')
        _login_as(client, uid)
        with app.app_context():
            for i in range(3):
                db.session.add(Event(
                    title=f'Pagination Extra {i}',
                    description=f'Extra event {i}',
                    date=datetime.now() + timedelta(days=100 + i),
                    required_skills='Test', slots=10, campus_id=1
                ))
            db.session.commit()
        resp = client.get('/opportunities?page=1')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Showing 1–9 of 12 opportunities' in body
        assert 'page=2' in body

    def test_filter_and_page_combined(self, client, app):
        uid = _create_user(app, email='combofilt@test.com')
        _login_as(client, uid)
        resp = client.get('/opportunities?campus=1&page=1')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body
        assert 'Green Campus Initiative' in body
        assert 'Sustainable Farming Demo' not in body

    def test_coordinator_status_filter(self, client, app):
        uid = _create_user(app, email='coordstatus@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/coordinator_dash?status=upcoming')
        assert resp.status_code == 200
        assert 'Upcoming' in resp.data.decode()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# J. Missing Features
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestMissingFeatures:

    def test_registration_has_only_one_attendance_record(self, app):
        volunteer_id = _create_user(
            app, email='uniqueattendance@test.com', role='volunteer', campus_id=1)
        with app.app_context():
            registration = Registration(
                user_id=volunteer_id, event_id=1, status='confirmed')
            db.session.add(registration)
            db.session.flush()
            db.session.add(Attendance(
                registration_id=registration.id, user_id=volunteer_id,
                event_id=1, status='present', hours_completed=1))
            db.session.commit()
            db.session.add(Attendance(
                registration_id=registration.id, user_id=volunteer_id,
                event_id=1, status='present', hours_completed=2))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_coordinator_cannot_access_director_analytics(self, client, app):
        uid = _create_user(app, email='coordscope@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/analytics')
        assert resp.status_code == 403

    def test_admin_can_access_director_analytics(self, client, app):
        uid = _create_user(app, email='adminanalytics@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/analytics')
        assert resp.status_code == 200

    def test_non_volunteer_cannot_register_for_event(self, client, app):
        uid = _create_user(app, email='coordregister@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.post('/opportunities/register/1')
        assert resp.status_code == 403
        with app.app_context():
            assert Registration.query.filter_by(user_id=uid).count() == 0

    def test_coordinator_activity_is_forced_to_assigned_campus(self, client, app):
        uid = _create_user(app, email='coordcampus@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.post('/create_activity', data={
            'title': 'Scoped Activity',
            'description': 'Must stay in the assigned campus.',
            'date': (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d'),
            'campus_id': '2',
            'slots': '10',
        })
        assert resp.status_code == 302
        with app.app_context():
            created = Event.query.filter_by(title='Scoped Activity').one()
            assert created.campus_id == 1

    def test_coordinator_cannot_update_other_campus_attendance(self, client, app):
        coordinator_id = _create_user(
            app, email='coordattendance@test.com', role='coordinator', campus_id=1)
        volunteer_id = _create_user(
            app, email='othercampusvol@test.com', role='volunteer', campus_id=2)
        with app.app_context():
            registration = Registration(
                user_id=volunteer_id, event_id=3, status='confirmed')
            db.session.add(registration)
            db.session.commit()
            registration_id = registration.id
        _login_as(client, coordinator_id)
        resp = client.post('/attendance', data={
            'event_id': '3',
            'registration_id': str(registration_id),
            'status': 'present',
            'hours_completed': '2',
        })
        assert resp.status_code == 403

    def test_present_attendance_sets_certificate_eligibility(self, client, app):
        coordinator_id = _create_user(
            app, email='certcoord@test.com', role='coordinator', campus_id=1)
        volunteer_id = _create_user(
            app, email='certvol@test.com', role='volunteer', campus_id=1)
        with app.app_context():
            db.session.get(Event, 1).date = datetime.now() - timedelta(days=1)
            registration = Registration(
                user_id=volunteer_id, event_id=1, status='confirmed')
            db.session.add(registration)
            db.session.commit()
            registration_id = registration.id
        _login_as(client, coordinator_id)
        resp = client.post('/attendance', data={
            'event_id': '1',
            'registration_id': str(registration_id),
            'status': 'present',
            'hours_completed': '2.5',
        })
        assert resp.status_code == 302
        with app.app_context():
            registration = db.session.get(Registration, registration_id)
            assert registration.status == 'completed'
            assert registration.certificate_eligible is True

    def test_absence_revokes_certificate_eligibility_without_duplicate(self, client, app):
        coordinator_id = _create_user(
            app, email='certrevoke@test.com', role='coordinator', campus_id=1)
        volunteer_id = _create_user(
            app, email='certrevokevol@test.com', role='volunteer', campus_id=1)
        with app.app_context():
            db.session.get(Event, 1).date = datetime.now() - timedelta(days=1)
            registration = Registration(
                user_id=volunteer_id, event_id=1, status='completed')
            db.session.add(registration)
            db.session.flush()
            db.session.add(Attendance(
                registration_id=registration.id, user_id=volunteer_id,
                event_id=1, status='present', hours_completed=2.5))
            db.session.commit()
            registration_id = registration.id
        _login_as(client, coordinator_id)
        resp = client.post('/attendance', data={
            'event_id': '1',
            'registration_id': str(registration_id),
            'status': 'absent',
            'hours_completed': '0',
        })
        assert resp.status_code == 302
        with app.app_context():
            registration = db.session.get(Registration, registration_id)
            assert registration.status == 'confirmed'
            assert registration.certificate_eligible is False
            assert Attendance.query.filter_by(
                registration_id=registration_id).count() == 1

    def test_coordinator_cannot_upload_to_other_campus_event(self, client, app):
        uid = _create_user(app, email='coordmilestone@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.post('/events/3/milestones')
        assert resp.status_code == 403

    def test_export_events_csv(self, client, app):
        uid = _create_user(app, email='evtcsv@test.com',
                           role='coordinator', campus_id=1)
        _login_as(client, uid)
        resp = client.get('/reports/events.csv')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'

    def test_export_campus_csv(self, client, app):
        uid = _create_user(app, email='camcsv@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/reports/campus.csv')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'
        assert b'Volunteer Participations' in resp.data

    def test_export_campus_pdf(self, client, app):
        uid = _create_user(app, email='campdf@test.com', role='director')
        _login_as(client, uid)
        resp = client.get('/reports/campus.pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF-')

    def test_admin_campus_filter(self, client, app):
        uid = _create_user(app, email='admfil@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/admin_dash?campus_id=1')
        assert resp.status_code == 200

    def test_admin_settings_get(self, client, app):
        uid = _create_user(app, email='admstg@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/settings')
        assert resp.status_code == 200

    def test_admin_settings_post(self, client, app):
        uid = _create_user(app, email='admstp@test.com', role='admin')
        _login_as(client, uid)
        resp = client.post('/settings', data={'max_slots_per_event': '120'},
                           follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            s = SystemSetting.query.filter_by(key='max_slots_per_event').first()
            assert s is not None
            assert s.value == '120'


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# K. Admin User Management
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestAdminUserManagement:

    def test_admin_create_user_get(self, client, app):
        uid = _create_user(app, email='acreateget@test.com', role='admin')
        _login_as(client, uid)
        resp = client.get('/admin/users/create')
        assert resp.status_code == 200

    def test_admin_create_user_post(self, client, app):
        uid = _create_user(app, email='acreatepost@test.com', role='admin')
        _login_as(client, uid)
        resp = client.post('/admin/users/create', data={
            'name': 'New User',
            'email': 'new@test.com',
            'password': 'password123',
            'role': 'coordinator',
            'campus_id': 1,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'User New User created successfully' in resp.data
        with app.app_context():
            u = User.query.filter_by(email='new@test.com').first()
            assert u is not None
            assert u.name == 'New User'
            assert u.role == 'coordinator'
            assert u.campus_id == 1
            entry = AuditLog.query.filter_by(
                action='user_created', target_id=u.id).first()
            assert entry is not None
            assert entry.actor_id == uid

    def test_admin_activity_log_requires_admin(self, client, app):
        volunteer_id = _create_user(
            app, email='auditvolunteer@test.com', role='volunteer')
        _login_as(client, volunteer_id)
        assert client.get('/admin_dash?tab=audit').status_code == 403

    def test_admin_csv_import_and_safe_export(self, client, app):
        admin_id = _create_user(app, email='csvadmin@test.com', role='admin')
        _login_as(client, admin_id)
        csv_text = (
            'name,email,password,role,campus_code,id_number,volunteer_type,college_affiliation\n'
            'CSV Volunteer,csvvolunteer@test.com,password123,volunteer,LINGAYEN,CSV-001,Student,\n')
        response = client.post('/admin/users/import', data={
            'file': (io.BytesIO(csv_text.encode()), 'users.csv'),
        }, content_type='multipart/form-data', follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            user = User.query.filter_by(email='csvvolunteer@test.com').first()
            assert user is not None
            assert AuditLog.query.filter_by(
                action='user_imported', target_id=user.id).first() is not None
        export = client.get('/admin/users/export.csv')
        assert export.status_code == 200
        assert b'password_hash' not in export.data
        assert b'csvvolunteer@test.com' in export.data

    def test_active_terms_are_required_and_recorded(self, client, app):
        admin_id = _create_user(app, email='termsadmin@test.com', role='admin')
        volunteer_id = _create_user(
            app, email='termsvolunteer@test.com', role='volunteer')
        with app.app_context():
            volunteer = db.session.get(User, volunteer_id)
            volunteer.set_password('password123')
            db.session.commit()
        _login_as(client, admin_id)
        published = client.post('/admin/terms', data={
            'title': 'PSU Volunteer Hub Terms', 'version': '1.0',
            'body': 'Use the system responsibly.',
        })
        assert published.status_code == 302
        client.post('/auth/logout')
        login = client.post('/auth/login', data={
            'identifier': 'termsvolunteer@test.com', 'password': 'password123',
        })
        assert login.headers['Location'].endswith('/auth/terms')
        accepted = client.post('/auth/terms', data={'accept_terms': 'on'})
        assert accepted.status_code == 302
        with app.app_context():
            revision = TermsRevision.query.filter_by(version='1.0').one()
            assert TermsAcceptance.query.filter_by(
                user_id=volunteer_id, revision_id=revision.id).first() is not None

    def test_admin_edit_user_get(self, client, app):
        with app.app_context():
            admin = User(name='EditGetAdmin', email='editget@test.com', role='admin')
            admin.set_password('pw')
            db.session.add(admin)
            db.session.commit()
            target_id = admin.id
        _login_as(client, target_id)
        resp = client.get(f'/admin/users/{target_id}/edit')
        assert resp.status_code == 200

    def test_admin_edit_user_post(self, client, app):
        with app.app_context():
            safety_admin = User(name='Safety Admin', email='safety@test.com',
                                role='admin')
            safety_admin.set_password('pw')
            admin = User(name='EditPostAdmin', email='editpost@test.com',
                         role='admin', campus_id=1)
            admin.set_password('pw')
            db.session.add_all([safety_admin, admin])
            db.session.commit()
            target_id = admin.id
        _login_as(client, target_id)
        resp = client.post(f'/admin/users/{target_id}/edit', data={
            'name': 'Updated Name',
            'email': 'updated@test.com',
            'role': 'director',
            'campus_id': 2,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Updated Name updated' in resp.data
        with app.app_context():
            u = db.session.get(User, target_id)
            assert u.name == 'Updated Name'
            assert u.email == 'updated@test.com'
            assert u.role == 'director'
            assert u.campus_id == 2

    @pytest.mark.parametrize('remember', [False, True])
    def test_admin_reset_own_password_requires_sign_in(self, client, app, remember):
        admin_id = _create_user(app, email='reset@test.com', password='oldpass123',
                                role='admin', name='ResetAdmin')
        assert client.post('/auth/login', data={
            'identifier': 'reset@test.com', 'password': 'oldpass123',
        }).status_code == 302
        # Keep coverage of cookies issued before remember-device sign-in was removed.
        with app.app_context():
            legacy_cookie = encode_cookie(str(admin_id))
        if remember:
            client.set_cookie('remember_token', legacy_cookie)
            assert client.get_cookie('remember_token') is not None
        other_session = app.test_client()
        with app.app_context():
            assert other_session.post('/auth/login', data={
                'identifier': 'reset@test.com', 'password': 'oldpass123',
            }).status_code == 302
        other_session.set_cookie('remember_token', legacy_cookie)
        resp = client.post(f'/admin/users/{admin_id}/reset-password', data={
            'new_password': 'newpass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == '/auth/login'
        assert b'Your password was reset. Sign in again with your new password.' in resp.data
        with client.session_transaction() as saved_session:
            assert '_user_id' not in saved_session
            assert 'auth_version' not in saved_session
        assert client.get_cookie('remember_token') is None
        # Simulate another browser restoring only its old remember cookie.
        with other_session.session_transaction() as saved_session:
            saved_session.clear()
        with app.app_context():
            expired = other_session.get('/admin_dash', follow_redirects=True)
        assert expired.request.path == '/auth/login'
        assert b'Your session expired because your password was changed. Sign in again.' in expired.data
        assert other_session.get_cookie('remember_token') is None
        with app.app_context():
            user = db.session.get(User, admin_id)
            assert user.auth_version == 2
            assert not user.check_password('oldpass123')
            assert user.check_password('newpass123')
            entry = AuditLog.query.filter_by(action='user_password_reset', target_id=admin_id).one()
            assert entry.actor_id == admin_id
        with app.app_context():
            rejected = client.post('/auth/login', data={
                'identifier': 'reset@test.com', 'password': 'oldpass123'})
            assert b'Invalid email/ID or password.' in rejected.data
            signed_in = client.post('/auth/login', data={
                'identifier': 'reset@test.com', 'password': 'newpass123'})
            assert signed_in.headers['Location'] == '/admin_dash'
        with client.session_transaction() as saved_session:
            assert saved_session['auth_version'] == 2

    @pytest.mark.parametrize('target_role', ['volunteer', 'admin'])
    def test_admin_reset_other_password_expires_target_sessions(self, client, app, target_role):
        admin_id = _create_user(app, email='reset-actor@test.com', role='admin')
        target_id = _create_user(app, email='reset-target@test.com', role=target_role,
                                 name='Reset Target')
        target_sessions = [app.test_client(), app.test_client()]
        for index, target_session in enumerate(target_sessions):
            with app.app_context():
                assert target_session.post('/auth/login', data={
                    'identifier': 'reset-target@test.com', 'password': 'password123',
                }).status_code == 302
                if index:
                    target_session.set_cookie('remember_token', encode_cookie(str(target_id)))
        assert target_sessions[1].get_cookie('remember_token') is not None
        _login_as(client, admin_id)
        response = client.post(f'/admin/users/{target_id}/reset-password', data={
            'new_password': 'replacement123'}, follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path == '/admin_dash'
        assert b'Password reset for Reset Target.' in response.data
        with client.session_transaction() as saved_session:
            assert saved_session['_user_id'] == str(admin_id)
            assert saved_session['auth_version'] == 1
        target_dashboard = '/admin_dash' if target_role == 'admin' else '/volunteer_dash'
        for target_session in target_sessions:
            with app.app_context():
                expired = target_session.get(target_dashboard, follow_redirects=True)
            assert expired.request.path == '/auth/login'
            assert b'Your session expired because your password was changed. Sign in again.' in expired.data
            assert target_session.get_cookie('remember_token') is None
            with target_session.session_transaction() as saved_session:
                assert '_user_id' not in saved_session
                assert 'auth_version' not in saved_session
        assert client.get('/admin_dash').status_code == 200
        with app.app_context():
            target = db.session.get(User, target_id)
            assert target.auth_version == 2
            assert not target.check_password('password123')
            assert target.check_password('replacement123')
            assert db.session.get(User, admin_id).auth_version == 1
            entry = AuditLog.query.filter_by(action='user_password_reset', target_id=target_id).one()
            assert entry.actor_id == admin_id

    @pytest.mark.parametrize('rejection', ['too-short', 'csrf'])
    def test_rejected_admin_reset_preserves_password_and_session(self, client, app, rejection):
        admin_id = _create_user(app, email='reset-rejected@test.com', role='admin')
        _login_as(client, admin_id)
        app.config['WTF_CSRF_ENABLED'] = rejection == 'csrf'
        response = client.post(f'/admin/users/{admin_id}/reset-password', data={
            'new_password': 'replacement123' if rejection == 'csrf' else 'short'})
        assert response.status_code == (400 if rejection == 'csrf' else 302)
        with app.app_context():
            user = db.session.get(User, admin_id)
            assert user.auth_version == 1
            assert user.check_password('password123')
            assert AuditLog.query.filter_by(action='user_password_reset').count() == 0
        with client.session_transaction() as saved_session:
            assert saved_session['_user_id'] == str(admin_id)
            assert saved_session['auth_version'] == 1


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# L. Reporting System (Coordinator / Director / Admin)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestReportingSystem:

    @pytest.mark.parametrize('mode, expected', [('include', 6), ('exclude', 4)])
    def test_director_multiple_campuses(self, app, client, monkeypatch, mode, expected):
        from flask import template_rendered
        self._director(app, client)
        self._add_event(app, 'Unassigned fixture', datetime(2026, 10, 20), campus_id=None)
        volunteer = _create_user(app, email='multi-attendance@test.com', sex='female')
        self._participate(app, volunteer, 1)
        self._participate(app, volunteer, 5)
        captured = []
        def record(sender, template, context, **extra):
            captured.append(context)
        query = [('campus', '1'), ('campus', '2'), ('campus', '1'), ('campus', '4'),
                 ('campus_mode', mode), ('campus_id', '9')]
        with template_rendered.connected_to(record, app):
            response = client.get('/analytics', query_string=query)
        assert response.status_code == 200
        context = captured[-1]
        assert context['selected_campuses'] == [1, 2, 4]
        assert context['live_summary']['event_count'] == expected
        assert context['live_summary']['total_attended'] == 1
        assert sum(row['actual_participants'] for row in context['sex_participation']) == 1
        assert len(context['dashboard_data']['activities']) == expected
        body = response.get_data(as_text=True)
        csv = client.get('/reports/university.csv', query_string=query).get_data(as_text=True)
        assert ('Youth Coding Mentor' in csv) == (mode == 'include')
        assert ('Unassigned fixture' in csv) == (mode == 'exclude')
        assert ('All campuses except:' if mode == 'exclude' else 'Selected campuses:') in csv
        labels = re.findall(r'<span>([^<]+)</span>', body.split('campus-filter__grid', 1)[1].split('</fieldset>', 1)[0])
        assert labels == sorted(labels, key=str.lower)
        def pdf(rows, summary, meta):
            assert summary['event_count'] == expected
            assert len(rows) == expected
            assert 'Lingayen' in meta['scope']
            return b'%PDF-scope'
        monkeypatch.setattr('app.routes.director.render_pdf', pdf)
        assert client.get('/reports/university.pdf', query_string=query).data == b'%PDF-scope'

    @pytest.mark.parametrize('query', [
        [('campus', '1'), ('campus', '9999')], [('campus', 'bad')],
        [('campus', '9' * 5000)], [('campus_mode', 'invalid')],
    ])
    def test_director_invalid_campus_selection(self, app, client, query):
        self._director(app, client)
        page = client.get('/analytics', query_string=query)
        assert page.status_code == 400
        body = page.get_data(as_text=True)
        assert 'role="alert"' in body and 'No activities match the current filters.' in body
        for extension in ('csv', 'pdf'):
            assert client.get('/reports/university.' + extension, query_string=query).status_code == 400

    def test_director_campus_paging_and_supplementary_forms(self, app, client, monkeypatch):
        self._director(app, client)
        for index in range(13):
            self._add_event(app, f'Multi-campus fixture {index}', datetime(2026, 10, 20),
                            campus_id=1 if index % 2 else 2)
        self._add_event(app, 'Multi-campus fixture excluded campus', datetime(2026, 10, 20), campus_id=3)
        self._add_event(app, 'Multi-campus fixture excluded category', datetime(2026, 10, 20), category='Health')
        self._add_event(app, 'Multi-campus fixture excluded date', datetime(2026, 11, 2))
        self._add_event(app, 'Different activity name', datetime(2026, 10, 20))
        query = [('campus', '1'), ('campus', '2'), ('campus_mode', 'include'),
                 ('activity_name', 'Multi-campus fixture'), ('category', 'Environment'),
                 ('start_date', '2026-10-01'), ('end_date', '2026-10-31')]
        body = client.get('/analytics', query_string=query).get_data(as_text=True)
        document = parse_html(body)
        links = [link.attrs['href'] for link in document.all('a')]
        next_page = next(link for link in links if 'page=2' in link)
        exports = [link for link in links if '/reports/university.' in link]
        assert {urlsplit(link).path for link in exports} == {'/reports/university.csv', '/reports/university.pdf'}
        for link in [next_page] + exports:
            parsed = parse_qs(urlsplit(link).query)
            assert parsed['campus'] == ['1', '2']
            assert parsed['campus_mode'] == ['include']
            assert parsed['activity_name'] == ['Multi-campus fixture']
        def titles(page):
            region = page.one('div', **{'aria-label': 'Live activity report table'})
            return [row.all('td')[0].text for row in region.one('tbody').all('tr')]
        first_titles = titles(document)
        second_titles = titles(parse_html(client.get(next_page).get_data(as_text=True)))
        expected = [f'Multi-campus fixture {index}' for index in reversed(range(13))]
        assert len(first_titles) == 10 and len(second_titles) == 3
        assert first_titles + second_titles == expected

        award = form_with_control(document, 'award_year', tags=('select',))
        values = form_values(award)
        assert values == {**{key: [value] for key, value in query if key != 'campus'},
                          'campus': ['1', '2'], 'view': ['live'], 'award_year': ['2026']}
        assert 'Historical Activities' not in body
        award_page = client.get('/analytics', query_string=values)
        assert award_page.status_code == 200
        assert titles(parse_html(award_page.get_data(as_text=True))) == first_titles

        def pdf(rows, summary, meta):
            assert [row['title'] for row in rows] == expected
            assert summary['event_count'] == 13
            return b'%PDF-reconciliation'
        monkeypatch.setattr('app.routes.director.render_pdf', pdf)
        for link in exports:
            response = client.get(link)
            assert response.status_code == 200
            if urlsplit(link).path.endswith('.pdf'):
                assert response.data == b'%PDF-reconciliation'
            else:
                rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
                header = next(index for index, row in enumerate(rows) if row and row[0] == 'Activity')
                assert [row[0] for row in rows[header + 1:] if row and row[0] != 'TOTAL'] == expected

    def test_historical_form_and_exports_keep_their_own_scope(self, app, client, monkeypatch):
        from app.models.event import HistoricalActivity
        from reportlab import platypus
        self._director(app, client)
        for index, (campus, year, kind, count) in enumerate([
                (1, 2022, 'Outreach', 7), (1, 2022, 'Outreach', 9),
                (2, 2022, 'Outreach', 30), (1, 2024, 'Outreach', 40),
                (1, 2022, 'Training', 50)]):
            db.session.add(HistoricalActivity(
                source_key=f'reconciliation-{index}', source_document='Synthetic QA source',
                source_page=1, source_row=index + 1, unit_name='Synthetic QA unit',
                title=f'Synthetic historical fixture {index}', campus_id=campus,
                year_conducted=year, activity_type=kind, volunteer_count=count))
        db.session.commit()
        response = client.get('/analytics', query_string={
            'view': 'historical', 'campus_id': '1', 'start_year': '2022', 'end_year': '2022',
            'activity_type': 'Outreach', 'campus': ['2', '3'], 'campus_mode': 'exclude',
            'category': 'Health', 'activity_name': 'Unrelated live selection', 'page': '2'})
        assert response.status_code == 200
        document = parse_html(response.get_data(as_text=True))
        expected = {'view': ['historical'], 'campus_id': ['1'], 'start_year': ['2022'],
                    'end_year': ['2022'], 'activity_type': ['Outreach']}
        historical = form_with_control(document, 'start_year')
        assert form_values(historical) == expected
        assert not historical.all('input', name='campus')
        assert not document.all('div', **{'aria-label': 'Live activity report table'})
        submitted = client.get('/analytics', query_string=form_values(historical))
        assert submitted.status_code == 200 and b'Historical Activities' in submitted.data
        links = [link.attrs['href'] for link in document.all('a')
                 if urlsplit(link.attrs.get('href', '')).path in ('/reports/campus.csv', '/reports/campus.pdf')]
        assert len(links) == 2
        rendered_tables = []
        original_table = platypus.Table
        def table(data, *args, **kwargs):
            rendered_tables.append(data)
            return original_table(data, *args, **kwargs)
        monkeypatch.setattr(platypus, 'Table', table)
        for link in links:
            assert parse_qs(urlsplit(link).query) == expected
            exported = client.get(link)
            assert exported.status_code == 200
            if urlsplit(link).path.endswith('.csv'):
                rows = list(csv.reader(io.StringIO(exported.get_data(as_text=True))))
                assert rows[1:] == [['Synthetic QA unit', '2', '16', '0']]
            else:
                assert exported.mimetype == 'application/pdf' and exported.data.startswith(b'%PDF-')
        assert rendered_tables[0][1:] == [['Synthetic QA unit', '2', '16', '0']]

    @pytest.mark.parametrize('mode', ['include', 'exclude'])
    def test_director_blank_campus_selection_means_all(self, app, client, mode):
        self._director(app, client)
        csv = client.get('/reports/university.csv', query_string={'campus_mode': mode}).get_data(as_text=True)
        assert 'Youth Coding Mentor' in csv and 'Community Food Drive' in csv

    def test_coordinator_ignores_multiple_campus_query(self, app, client):
        self._coord(app, client, 1)
        query = [('campus', '2'), ('campus_mode', 'exclude'), ('campus_id', '2')]
        csv = client.get('/reports/events.csv', query_string=query).get_data(as_text=True)
        assert 'Youth Coding Mentor' in csv and 'Community Food Drive' not in csv

    def test_director_all_campuses_excluded_and_legacy_links(self, app, client):
        self._director(app, client)
        self._add_event(app, 'Unassigned fixture', datetime(2026, 10, 20), campus_id=None)
        query = [('campus', str(cid)) for cid in range(1, 10)] + [('campus_mode', 'exclude')]
        csv = client.get('/reports/university.csv', query_string=query).get_data(as_text=True)
        assert 'Unassigned fixture' in csv and 'Youth Coding Mentor' not in csv
        legacy = client.get('/reports/university.csv?campus_id=1').get_data(as_text=True)
        assert 'Youth Coding Mentor' in legacy and 'Community Food Drive' not in legacy
        # Explicit empty live selection does not inherit the historical campus.
        all_rows = client.get('/reports/university.csv?campus_id=1&campus_mode=include').get_data(as_text=True)
        assert 'Community Food Drive' in all_rows and 'Unassigned fixture' in all_rows

    def test_activity_search_participation_and_literal_symbols(self, app):
        from app.reports import build_events_report, render_pdf, _build_meta
        from app.dashboard import summarize_report
        uid = _create_user(app, email='searched-attendance@test.com', sex='female')
        event_id = self._add_event(app, '100%_Clean <campus>', datetime(2026, 10, 20))
        self._participate(app, uid, event_id)
        with app.app_context():
            rows, summary = build_events_report(
                activity_name='%_clean', campus_id=1, category='Environment',
                start_date='2026-10-01', end_date='2026-10-31')
            assert [row['event_id'] for row in rows] == [event_id]
            assert summary['total_registrations'] == summary['total_attended'] == 1
            assert summarize_report(rows)['monthly']['primary'] == [1]
            assert sum(row['actual_participants'] for row in
                       AnalyticsAggregator.sex_participation(activity_name='no-match')) == 0
            assert sum(row['actual_participants'] for row in
                       AnalyticsAggregator.sex_participation(activity_name='%_CLEAN')) == 1
            meta = _build_meta('Search report', 'All Campuses', '', '', '')
            meta['activity_name'] = '<campus> & %_Clean'
            assert render_pdf(rows, summary, meta).startswith(b'%PDF-')

    @pytest.mark.parametrize('term, expected', [
        ('  cLeAnUp  ', ['Coastal Cleanup Drive']),
        ('%', []), ('_', []), ('not-an-activity', []),
        ('   ', None),
    ])
    def test_activity_name_literal_search(self, app, term, expected):
        from app.reports import build_events_report
        with app.app_context():
            rows, summary = build_events_report(activity_name=term)
            assert summary['event_count'] == len(rows)
            if expected is None:
                assert len(rows) == 9
            else:
                assert [row['title'] for row in rows] == expected

    @pytest.mark.parametrize('role', ['director', 'coordinator'])
    def test_activity_search_page_charts_and_exports(self, app, client, monkeypatch, role):
        from flask import template_rendered
        uid = _create_user(app, email=f'search-{role}@test.com', role=role, campus_id=1)
        _login_as(client, uid)
        captured = []

        def record(sender, template, context, **extra):
            captured.append(context)

        query = {'activity_name': '  cLeAnUp  ', 'campus_id': '2'}
        path = '/analytics' if role == 'director' else '/coordinator_analytics'
        with template_rendered.connected_to(record, app):
            response = client.get(path, query_string=query)
        assert response.status_code == 200
        context = captured[-1]
        summary = context['live_summary'] if role == 'director' else context['report_summary']
        assert summary['event_count'] == (0 if role == 'director' else 1)
        assert len(context['dashboard_data']['activities']) == summary['event_count']
        assert sum(context['dashboard_data']['monthly']['primary']) == summary['total_registrations']
        body = response.get_data(as_text=True)
        assert 'name="activity_name"' in body
        assert 'value="  cLeAnUp  "' in body
        prefix = '/reports/university' if role == 'director' else '/reports/events'
        csv = client.get(prefix + '.csv', query_string=query)
        assert csv.status_code == 200
        assert ('Coastal Cleanup Drive' in csv.get_data(as_text=True)) == (role == 'coordinator')
        assert 'Youth Coding Mentor' not in csv.get_data(as_text=True)
        assert 'Activity name contains: cLeAnUp' in csv.get_data(as_text=True)

        def fake_pdf(rows, report_summary, meta):
            assert report_summary == summary
            assert len(rows) == summary['event_count']
            assert meta['activity_name'] == 'cLeAnUp'
            return b'%PDF-test'

        monkeypatch.setattr(f'app.routes.{role}.render_pdf', fake_pdf)
        assert client.get(prefix + '.pdf', query_string=query).data == b'%PDF-test'


    # â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _coord(self, app, client, campus_id=1):
        uid = _create_user(app, email=f'coord{ campus_id }@test.com',
                           role='coordinator', campus_id=campus_id)
        _login_as(client, uid)
        return uid

    def _director(self, app, client):
        uid = _create_user(app, email='dirrep@test.com', role='director')
        _login_as(client, uid)
        return uid

    def _admin(self, app, client):
        uid = _create_user(app, email='adminrep@test.com', role='admin')
        _login_as(client, uid)
        return uid

    def _add_event(self, app, title, date, campus_id=1, category='Environment'):
        with app.app_context():
            e = Event(title=title, description='report test event',
                      date=date, required_skills='Teaching', slots=10,
                      campus_id=campus_id, category=category)
            db.session.add(e)
            db.session.commit()
            return e.id

    def _participate(self, app, user_id, event_id, attended=True, hours=2.0,
                    status='completed'):
        with app.app_context():
            reg = Registration(user_id=user_id, event_id=event_id, status=status)
            db.session.add(reg)
            db.session.flush()
            if attended:
                db.session.add(Attendance(
                    registration_id=reg.id, user_id=user_id, event_id=event_id,
                    status='present', hours_completed=hours))
            db.session.commit()

    # â”€â”€ Coordinator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_coordinator_csv_export(self, client, app):
        self._coord(app, client, 1)
        resp = client.get('/reports/events.csv')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body
        assert 'Registrations' in body

    def test_coordinator_pdf_export(self, client, app):
        self._coord(app, client, 1)
        resp = client.get('/reports/events.pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF-')

    def test_coordinator_campus_scoping(self, client, app):
        self._coord(app, client, 1)
        resp = client.get('/reports/events.csv')
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body        # campus 1
        assert 'Community Food Drive' not in body   # campus 2
        assert 'Disaster Response Training' not in body  # campus 3
        assert 'PSU Volunteer Hub' in body

    def test_coordinator_forged_campus_filter(self, client, app):
        # Coordinator (campus 1) tries to leak campus 2 via ?campus_id=2.
        self._coord(app, client, 1)
        resp = client.get('/reports/events.csv?campus_id=2')
        body = resp.data.decode()
        assert 'Community Food Drive' not in body   # leak prevented
        assert 'Youth Coding Mentor' in body        # own campus still present

    # â”€â”€ Director â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_director_csv_export(self, client, app):
        self._director(app, client)
        resp = client.get('/reports/university.csv')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body        # campus 1
        assert 'Community Food Drive' in body       # campus 2 (cross-campus)

    def test_director_pdf_export(self, client, app):
        self._director(app, client)
        resp = client.get('/reports/university.pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF-')

    def test_director_campus_filter(self, client, app):
        self._director(app, client)
        resp = client.get('/reports/university.csv?campus_id=2')
        body = resp.data.decode()
        assert 'Community Food Drive' in body
        assert 'Youth Coding Mentor' not in body

    def test_director_all_campuses_default(self, client, app):
        self._director(app, client)
        resp = client.get('/reports/university.csv')
        body = resp.data.decode()
        # No campus selected => university-wide (multiple campuses present)
        assert 'All Campuses' in body

    # â”€â”€ Admin (shares director reporting, role-aware) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_admin_reporting_csv(self, client, app):
        self._admin(app, client)
        resp = client.get('/reports/university.csv')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/csv'
        assert 'University-wide Activity Report' in resp.data.decode()

    def test_admin_reporting_pdf(self, client, app):
        self._admin(app, client)
        resp = client.get('/reports/university.pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF-')

    def test_admin_branding_not_director_console(self, client, app):
        self._admin(app, client)
        resp = client.get('/analytics')
        body = resp.data.decode()
        assert 'Director Console' not in body
        assert 'Administration' in body

    # â”€â”€ Filters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_date_filtering(self, client, app):
        self._coord(app, client, 1)
        self._add_event(app, 'Dated Event A', datetime(2024, 6, 1), 1)
        self._add_event(app, 'Dated Event B', datetime(2023, 6, 1), 1)
        resp = client.get('/reports/events.csv?start_date=2024-01-01')
        body = resp.data.decode()
        assert 'Dated Event A' in body
        assert 'Dated Event B' not in body

    def test_end_date_excludes_later(self, client, app):
        self._coord(app, client, 1)
        self._add_event(app, 'Early Event', datetime(2024, 1, 15), 1)
        self._add_event(app, 'Late Event', datetime(2024, 12, 15), 1)
        resp = client.get('/reports/events.csv?end_date=2024-06-30')
        body = resp.data.decode()
        assert 'Early Event' in body
        assert 'Late Event' not in body

    def test_category_filtering(self, client, app):
        self._coord(app, client, 1)
        resp = client.get('/reports/events.csv?category=Environment')
        body = resp.data.decode()
        assert 'Green Campus Initiative' in body
        assert 'Coastal Cleanup Drive' in body
        assert 'Youth Coding Mentor' not in body

    def test_combined_filters(self, client, app):
        self._coord(app, client, 1)
        resp = client.get(
            '/reports/events.csv?category=Environment&start_date=2000-01-01')
        body = resp.data.decode()
        assert 'Green Campus Initiative' in body
        assert 'Coastal Cleanup Drive' in body
        assert 'Youth Coding Mentor' not in body

    def test_invalid_date_range_coordinator(self, client, app):
        self._coord(app, client, 1)
        # start_date after end_date must fail safely with 400
        resp = client.get(
            '/reports/events.csv?start_date=2025-12-31&end_date=2025-01-01')
        assert resp.status_code == 400

    def test_invalid_date_range_director(self, client, app):
        self._director(app, client)
        resp = client.get(
            '/reports/university.csv?start_date=2025-12-31&end_date=2025-01-01')
        assert resp.status_code == 302  # redirected with a validation message

    def test_empty_report_handled(self, client, app):
        self._coord(app, client, 1)
        resp = client.get('/reports/events.csv?category=NoSuchCategory')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'TOTAL' in body
        assert '0' in body

    def test_csv_and_pdf_use_same_dataset(self, client, app):
        self._coord(app, client, 1)
        with app.app_context():
            expected = {e.title for e in Event.query.filter_by(campus_id=1).all()}
        csv_resp = client.get('/reports/events.csv')
        csv_body = csv_resp.data.decode()
        for title in expected:
            assert title in csv_body
        pdf_resp = client.get('/reports/events.pdf')
        assert pdf_resp.status_code == 200
        assert pdf_resp.data.startswith(b'%PDF-')

    def test_unauthorized_role_denied(self, client, app):
        uid = _create_user(app, email='volrep@test.com', role='volunteer')
        _login_as(client, uid)
        assert client.get('/reports/events.csv').status_code == 403
        assert client.get('/reports/university.csv').status_code == 403

    def test_pdf_generation_with_reportlab(self, client, app):
        # Regression: reportlab must be installed and produce a valid PDF.
        self._director(app, client)
        resp = client.get('/reports/university.pdf')
        assert resp.status_code == 200
        assert resp.data[:5] == b'%PDF-'

    def test_report_includes_aggregates(self, client, app):
        self._coord(app, client, 1)
        with app.app_context():
            eid = Event.query.filter_by(title='Green Campus Initiative').first().id
            vid = _create_user(app, email='repvol@test.com',
                               role='volunteer', campus_id=1)
        self._participate(app, vid, eid, attended=True, hours=3.0,
                         status='completed')
        resp = client.get('/reports/events.csv')
        body = resp.data.decode()
        assert 'Service Hours' not in body
        assert 'Hours' not in body
        assert 'TOTAL' in body


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# M. Outsider / External Volunteer Workflow (Phase 12)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestOutsiderVolunteers:

    def _coordinator(self, app, client, campus_id=1):
        uid = _create_user(app, email=f'extcoord{campus_id}@test.com',
                           role='coordinator', campus_id=campus_id)
        _login_as(client, uid)
        return uid

    def _event_id(self, app, title='Youth Coding Mentor'):
        with app.app_context():
            return Event.query.filter_by(title=title).first().id

    @staticmethod
    def _external_registration(app, event_id, id_number='EXT-TEST',
                               email='external@example.com'):
        with app.app_context():
            participant = ExternalParticipant(
                id_number=id_number, name='External Volunteer', email=email)
            db.session.add(participant)
            db.session.flush()
            registration = Registration(
                external_participant_id=participant.id, event_id=event_id,
                status='confirmed')
            db.session.add(registration)
            db.session.commit()
            return registration.id

    # â”€â”€ Public Join workflow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_retired_public_join_redirects_to_psu_sign_in(self, client, app):
        eid = self._event_id(app)
        response = client.get(f'/event/{eid}/join?external=1')
        target = urlsplit(response.location)
        assert response.status_code == 302
        assert target.path == '/auth/login'
        assert parse_qs(target.query)['next'] == [
            f'/opportunities/register/{eid}']

    def test_retired_guest_submission_creates_no_records(self, client, app):
        eid = self._event_id(app)
        with app.app_context():
            participant_count = ExternalParticipant.query.count()
            registration_count = Registration.query.count()
        response = client.post(f'/event/{eid}/join', data={
            'from_psu': 'no',
            'name': 'Former Guest',
            'email': 'former.guest@example.com',
        })
        assert response.status_code == 302
        with app.app_context():
            assert ExternalParticipant.query.count() == participant_count
            assert Registration.query.count() == registration_count

    def test_public_opportunity_card_requires_psu_sign_in(self, client, app):
        eid = self._event_id(app)
        body = client.get('/opportunities').get_data(as_text=True)
        assert f'href="/opportunities/{eid}"' in body
        assert 'View details' in body
        assert 'Sign in to join' in client.get(f'/opportunities/{eid}').get_data(as_text=True)
        assert 'Register as an external volunteer' not in body
        assert f'/event/{eid}/join?external=1' not in body

    def test_home_join_actions_require_psu_sign_in(self, client, app):
        body = client.get('/').get_data(as_text=True)
        assert 'Sign in to join' in body
        assert '/event/' not in body

    def test_guest_link_shows_only_signed_registration(self, client, app):
        from app.routes.events import _external_token

        eid = self._event_id(app)
        registration_id = self._external_registration(
            app, eid, id_number='EXT-MANAGE', email='manage@example.com')
        with app.app_context():
            registration = db.session.get(Registration, registration_id)
            token = _external_token(registration)
        response = client.get(f'/external/registrations/{token}')
        assert response.status_code == 200
        assert 'External volunteer registration' in response.get_data(as_text=True)

    def test_guest_link_expiry_is_not_disclosed(self, client, app, monkeypatch):
        from app.routes import events as events_routes
        from app.routes.events import _external_token

        eid = self._event_id(app)
        registration_id = self._external_registration(
            app, eid, id_number='EXT-EXPIRED', email='expired@example.com')
        with app.app_context():
            registration = db.session.get(Registration, registration_id)
            token = _external_token(registration)
        monkeypatch.setattr(events_routes, 'EXTERNAL_LINK_MAX_AGE', -1)
        response = client.get(f'/external/registrations/{token}')
        assert response.status_code == 404
        assert 'Registration link unavailable' in response.get_data(as_text=True)

    def test_psu_user_still_uses_normal_flow(self, client, app):
        eid = self._event_id(app)
        uid = _create_user(app, email='psujoin@test.com',
                           role='volunteer', campus_id=1)
        with app.app_context():
            db.session.get(User, uid).sex = 'male'
            db.session.commit()
        _login_as(client, uid)
        resp = client.post(f'/opportunities/register/{eid}', data={'accept_agreement': 'yes'}, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            reg = Registration.query.filter_by(
                user_id=uid, event_id=eid).first()
            assert reg is not None

    # â”€â”€ Coordinator manual encoding â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_coordinator_can_manually_add_outsider(self, client, app):
        self._coordinator(app, client, 1)
        eid = self._event_id(app)  # campus 1
        resp = client.post(
            f'/coordinator/events/{eid}/external',
            data={'id_number': 'EXT-MAN-1', 'name': 'Manual Outsider', 'sex': 'female'})
        assert resp.status_code == 302
        with app.app_context():
            ep = ExternalParticipant.query.filter_by(
                id_number='EXT-MAN-1').first()
            assert ep is not None
            assert ep.sex == 'female'
            assert Registration.query.filter_by(
                external_participant_id=ep.id, event_id=eid).first() is not None

    def test_coordinator_cannot_add_other_campus_outsider(self, client, app):
        self._coordinator(app, client, 1)
        # Community Food Drive is campus 2
        with app.app_context():
            eid = Event.query.filter_by(title='Community Food Drive').first().id
        resp = client.post(
            f'/coordinator/events/{eid}/external',
            data={'id_number': 'EXT-X'})
        assert resp.status_code == 403
        with app.app_context():
            assert ExternalParticipant.query.filter_by(
                id_number='EXT-X').first() is None

    def test_guest_cancellation_reaches_only_the_owning_campus_queue(self, client, app):
        from app.routes.events import _external_token

        eid = self._event_id(app)
        self._coordinator(app, client, 1)
        registration_id = self._external_registration(
            app, eid, id_number='EXT-CANCEL', email='cancel@example.com')
        with app.app_context():
            registration = db.session.get(Registration, registration_id)
            token = _external_token(registration)
        response = client.post(
            f'/external/registrations/{token}/cancel',
            data={'reason': 'Academic Conflict'},
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(
                Registration, registration.id).cancellation_request is not None
        response = client.get('/coordinator/cancellation-requests')
        assert response.status_code == 200
        assert 'External Volunteer' in response.get_data(as_text=True)
        with app.app_context():
            assert CancellationRequest.query.join(Registration).join(Event).filter(
                Event.campus_id == 2).count() == 0

    # â”€â”€ Attendance integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_attendance_for_outsider(self, client, app):
        self._coordinator(app, client, 1)
        eid = self._event_id(app)
        with app.app_context():
            db.session.get(Event, eid).date = datetime.now() - timedelta(days=1)
            ep = ExternalParticipant(id_number='EXT-ATT')
            db.session.add(ep)
            db.session.commit()
            reg = Registration(external_participant_id=ep.id, event_id=eid,
                               status='confirmed')
            db.session.add(reg)
            db.session.commit()
            reg_id = reg.id
        resp = client.post('/attendance', data={
            'event_id': str(eid),
            'registration_id': str(reg_id),
            'status': 'present',
            'hours_completed': '2.5',
        })
        assert resp.status_code == 302
        with app.app_context():
            att = Attendance.query.filter_by(registration_id=reg_id).first()
            assert att is not None
            assert att.user_id is None
            assert att.status == 'present'

    def test_outsider_attendance_no_duplicate(self, client, app):
        self._coordinator(app, client, 1)
        eid = self._event_id(app)
        with app.app_context():
            db.session.get(Event, eid).date = datetime.now() - timedelta(days=1)
            ep = ExternalParticipant(id_number='EXT-DUP')
            db.session.add(ep)
            db.session.commit()
            reg = Registration(external_participant_id=ep.id, event_id=eid,
                               status='confirmed')
            db.session.add(reg)
            db.session.commit()
            reg_id = reg.id
        client.post('/attendance', data={
            'event_id': str(eid), 'registration_id': str(reg_id),
            'status': 'present', 'hours_completed': '1'})
        client.post('/attendance', data={
            'event_id': str(eid), 'registration_id': str(reg_id),
            'status': 'present', 'hours_completed': '2'})
        with app.app_context():
            assert Attendance.query.filter_by(registration_id=reg_id).count() == 1

    def test_outsider_certificate_eligibility(self, client, app):
        self._coordinator(app, client, 1)
        eid = self._event_id(app)
        with app.app_context():
            db.session.get(Event, eid).date = datetime.now() - timedelta(days=1)
            ep = ExternalParticipant(id_number='EXT-CERT')
            db.session.add(ep)
            db.session.commit()
            reg = Registration(external_participant_id=ep.id, event_id=eid,
                               status='confirmed')
            db.session.add(reg)
            db.session.commit()
            reg_id = reg.id
        client.post('/attendance', data={
            'event_id': str(eid), 'registration_id': str(reg_id),
            'status': 'present', 'hours_completed': '3'})
        with app.app_context():
            reg = db.session.get(Registration, reg_id)
            assert reg.status == 'completed'
            assert reg.certificate_eligible is True

    def test_outsider_appears_in_report(self, client, app):
        self._coordinator(app, client, 1)
        eid = self._event_id(app)
        client.post(f'/event/{eid}/join', data={
            'from_psu': 'no', 'id_number': 'EXT-REP'})
        resp = client.get('/reports/events.csv')
        body = resp.data.decode()
        assert 'External' in body  # breakdown column present
        assert 'EXT-REP' in body or 'External #EXT-REP' in body or \
            'Youth Coding Mentor' in body

    def test_existing_psu_registration_intact(self, client, app):
        uid = _create_user(app, email='psureg@test.com',
                           role='volunteer', campus_id=1)
        _login_as(client, uid)
        eid = self._event_id(app)
        resp = client.post(f'/opportunities/register/{eid}',
                           data={'accept_agreement': 'yes'},
                           follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert Registration.query.filter_by(
                user_id=uid, event_id=eid).first() is not None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# O. Coordinator Event Editing (Phase 16)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestCoordinatorEventEditing:
    def _coord(self, app, campus_id=1, email='coord@test.com'):
        return _create_user(app, email=email, role='coordinator',
                           campus_id=campus_id, name='Coord')

    def test_own_campus_edit_succeeds(self, app, client):
        cid = self._coord(app, 1)
        _login_as(client, cid)
        resp = client.post('/coordinator/events/1/edit', data={
            'title': 'Updated Title', 'description': 'Updated desc',
            'date': '2030-01-01', 'location': 'New Loc',
            'category': 'Education & Literacy', 'slots': 25,
            'required_skills': 'Teaching'}, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            e = db.session.get(Event, 1)
            assert e.title == 'Updated Title'
            assert e.slots == 25

    def test_cross_campus_edit_denied(self, app, client):
        # Event id 3 belongs to campus 2; coordinator is campus 1.
        cid = self._coord(app, 1)
        _login_as(client, cid)
        assert client.get(f'/coordinator/events/3/edit').status_code == 403
        resp = client.post(f'/coordinator/events/3/edit', data={
            'title': 'X', 'description': 'Y', 'date': '2030-01-01', 'slots': 5})
        assert resp.status_code == 403

    def test_volunteer_cannot_edit(self, app, client):
        vid = _create_user(app, email='vol@test.com', role='volunteer',
                          campus_id=1)
        _login_as(client, vid)
        assert client.get('/coordinator/events/1/edit').status_code in (302, 403)

    def test_director_cannot_edit(self, app, client):
        did = _create_user(app, email='dir@test.com', role='director',
                          campus_id=1)
        _login_as(client, did)
        assert client.get('/coordinator/events/1/edit').status_code in (302, 403)

    def test_invalid_values_rejected(self, app, client):
        cid = self._coord(app, 1)
        _login_as(client, cid)
        with app.app_context():
            orig = db.session.get(Event, 1).title
        resp = client.post('/coordinator/events/1/edit', data={
            'title': '', 'description': 'x', 'date': '2030-01-01',
            'slots': 5}, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Event, 1).title == orig  # unchanged

    def test_slots_below_registrations_rejected(self, app, client):
        with app.app_context():
            ev = Event(title='Cap Event', description='d',
                       date=datetime.now() + timedelta(days=5),
                       required_skills='', slots=10, campus_id=1,
                       category='General')
            db.session.add(ev)
            db.session.commit()
            eid = ev.id
            vid = _create_user(app, email='volcap@test.com', role='volunteer',
                              campus_id=1)
            db.session.add(Registration(user_id=vid, event_id=eid,
                                        status='confirmed'))
            db.session.commit()
        cid = self._coord(app, 1, email='coordcap@test.com')
        _login_as(client, cid)
        resp = client.post(f'/coordinator/events/{eid}/edit', data={
            'title': 'Cap Event', 'description': 'd',
            'date': (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'slots': 0, 'category': 'General', 'required_skills': ''},
            follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Event, eid).slots == 10  # unchanged

    def test_registrations_survive_edit(self, app, client):
        with app.app_context():
            ev = Event(title='Keep Event', description='d',
                       date=datetime.now() + timedelta(days=5),
                       required_skills='', slots=10, campus_id=1,
                       category='General')
            db.session.add(ev)
            db.session.commit()
            eid = ev.id
            vid = _create_user(app, email='volkeep@test.com', role='volunteer',
                              campus_id=1)
            db.session.add(Registration(user_id=vid, event_id=eid,
                                        status='confirmed'))
            db.session.commit()
            rid = Registration.query.filter_by(event_id=eid).first().id
        cid = self._coord(app, 1, email='coordkeep@test.com')
        _login_as(client, cid)
        client.post(f'/coordinator/events/{eid}/edit', data={
            'title': 'Keep Event', 'description': 'updated',
            'date': (datetime.now() + timedelta(days=6)).strftime('%Y-%m-%d'),
            'slots': 12, 'category': 'General', 'required_skills': ''},
            follow_redirects=True)
        with app.app_context():
            reg = db.session.get(Registration, rid)
            assert reg is not None
            assert reg.event_id == eid

    def test_csrf_blocks_edit_without_token(self, app, client):
        app.config['WTF_CSRF_ENABLED'] = True
        cid = self._coord(app, 1, email='coordcsrf@test.com')
        _login_as(client, cid)
        resp = client.post('/coordinator/events/1/edit', data={
            'title': 'X', 'description': 'Y', 'date': '2030-01-01', 'slots': 5},
            follow_redirects=False)
        assert resp.status_code in (400, 302)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# N. Analytics & Chart Improvements (Phase 18)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

from app.recommendation.analytics import AnalyticsAggregator


class TestAnalytics:
    """Deterministic descriptive-analytics tests (Phase 18).

    Isolated scenarios use campus 5 (Bayambang) which has NO seed events, so
    counts are fully controlled.
    """

    def _event(self, app, title, date, campus_id=5, category='Environment',
               slots=10):
        with app.app_context():
            e = Event(title=title, description='t', date=date,
                      required_skills='', slots=slots, campus_id=campus_id,
                      category=category)
            db.session.add(e)
            db.session.commit()
            return e.id

    def _reg(self, app, user_id=None, external_id=None, event_id=None,
             status='completed', attendance_status='present', hours=2.0):
        with app.app_context():
            reg = Registration(user_id=user_id,
                               external_participant_id=external_id,
                               event_id=event_id, status=status)
            db.session.add(reg)
            db.session.flush()
            if attendance_status:
                db.session.add(Attendance(
                    registration_id=reg.id, user_id=user_id,
                    event_id=event_id, status=attendance_status,
                    hours_completed=hours if attendance_status == 'present'
                    else 0.0))
            db.session.commit()
            return reg.id

    def _vol(self, app, email='vol@test.com'):
        return _create_user(app, email=email, role='volunteer', campus_id=5,
                            name='V')

    # â”€â”€ Core metric definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_registration_count_excludes_cancelled(self, app):
        eid = self._event(app, 'A', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        v1 = self._vol(app, 'a1@t.com')
        v2 = self._vol(app, 'a2@t.com')
        self._reg(app, user_id=v1, event_id=eid, status='completed',
                  attendance_status='present')
        self._reg(app, user_id=v2, event_id=eid, status='cancelled',
                  attendance_status=None)
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
        assert s['registrations'] == 1          # cancelled excluded
        assert s['attended'] == 1
        assert s['conversion_rate'] == 100.0

    def test_unique_volunteers_distinct_from_registrations(self, app):
        e1 = self._event(app, 'A', datetime.now() + timedelta(days=1), 5,
                         'Environment')
        e2 = self._event(app, 'B', datetime.now() + timedelta(days=2), 5,
                         'Environment')
        v = self._vol(app, 'u1@t.com')
        self._reg(app, user_id=v, event_id=e1, status='completed',
                  attendance_status='present')
        self._reg(app, user_id=v, event_id=e2, status='completed',
                  attendance_status='present')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
        assert s['registrations'] == 2           # two sign-ups
        assert s['unique_volunteers'] == 1       # same person

    def test_attendance_count_and_absent(self, app):
        eid = self._event(app, 'A', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        p = self._vol(app, 'p@t.com')
        a = self._vol(app, 'ab@t.com')
        self._reg(app, user_id=p, event_id=eid, status='completed',
                  attendance_status='present')
        self._reg(app, user_id=a, event_id=eid, status='completed',
                  attendance_status='absent')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
        assert s['registrations'] == 2
        assert s['attended'] == 1               # only present counted
        assert s['attendance_rate'] == 50.0
        assert s['conversion_rate'] == 50.0

    def test_zero_registrations_safe(self, app):
        self._event(app, 'Empty', datetime.now() + timedelta(days=1), 5,
                    'Environment')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
        assert s['registrations'] == 0
        assert s['attended'] == 0
        assert s['attendance_rate'] == 0.0
        assert s['conversion_rate'] == 0.0
        assert s['unique_volunteers'] == 0

    def test_prefer_not_to_say_is_separate_from_unrecorded_data(self, app):
        from app.reports import build_events_report

        event_id = self._event(
            app, 'Demographics', datetime.now() + timedelta(days=1), 5)
        private_user_id = self._vol(app, 'private-demographics@test.com')
        legacy_user_id = self._vol(app, 'legacy-demographics@test.com')
        with app.app_context():
            db.session.get(User, private_user_id).sex = 'prefer_not_to_say'
            db.session.get(User, legacy_user_id).sex = None
            db.session.commit()
        self._reg(app, user_id=private_user_id, event_id=event_id)
        self._reg(app, user_id=legacy_user_id, event_id=event_id)
        with app.app_context():
            rows = AnalyticsAggregator.sex_participation(campus_id=5)
            counts = {row['sex']: row['actual_participants'] for row in rows}
            _, private_summary = build_events_report(
                campus_id=5, sex='prefer_not_to_say')
            _, legacy_summary = build_events_report(
                campus_id=5, sex='unrecorded')
        assert counts['Prefer Not to Say'] == 1
        assert counts['Not recorded'] == 1
        assert private_summary['total_registrations'] == 1
        assert legacy_summary['total_registrations'] == 1

    def test_sex_participation_includes_external_volunteers(self, app):
        event_id = self._event(app, 'External demographics', datetime.now() + timedelta(days=1), 5)
        with app.app_context():
            external = ExternalParticipant(id_number='EXT-SEX', sex='female')
            db.session.add(external)
            db.session.commit()
            external_id = external.id
        self._reg(app, external_id=external_id, event_id=event_id)
        with app.app_context():
            rows = AnalyticsAggregator.sex_participation(campus_id=5, sex='female')
        assert rows == [{'sex': 'Female', 'actual_participants': 1}]

    def test_analytics_matches_report(self, app):
        # Phase 18.4: dashboard/CSV/PDF must agree for the same scope.
        from app.reports import build_events_report
        eid = self._event(app, 'A', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        v = self._vol(app, 'm@t.com')
        self._reg(app, user_id=v, event_id=eid, status='completed',
                  attendance_status='present')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
            _, rep = build_events_report(campus_id=5)
        assert s['registrations'] == rep['total_registrations']
        assert s['attended'] == rep['total_attended']

    # â”€â”€ Scope / security â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_coordinator_analytics_campus_scoped(self, app, client):
        cid = _create_user(app, email='coord_an@t.com', role='coordinator',
                           campus_id=1, name='C')
        _login_as(client, cid)
        resp = client.get('/coordinator_analytics')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Youth Coding Mentor' in body        # campus 1 event
        assert 'Community Food Drive' not in body  # campus 2 leaked

    def test_director_accesses_university_analytics(self, app, client):
        did = _create_user(app, email='dir_an@t.com', role='director')
        _login_as(client, did)
        resp = client.get('/analytics')
        assert resp.status_code == 200
        assert 'Cross-Campus Comparison' in resp.data.decode()

    def test_live_activity_report_paginates_at_ten_rows(self, app, client):
        director_id = _create_user(app, email='page_dir@test.com', role='director')
        with app.app_context():
            for index in range(2):
                db.session.add(Event(title=f'Report Page {index}', description='Pagination test',
                    date=datetime.now() + timedelta(days=70 + index), slots=10, campus_id=1))
            db.session.commit()
        _login_as(client, director_id)

        first_page = client.get('/analytics?page=1').get_data(as_text=True)
        second_page = client.get('/analytics?page=2').get_data(as_text=True)
        assert 'Page 1' in first_page and 'Page 2' in first_page
        assert 'Coastal Cleanup Drive' not in first_page
        assert 'Coastal Cleanup Drive' in second_page

    @pytest.mark.parametrize('scope', ['include', 'exclude', 'legacy'])
    def test_report_pagination_and_exports_preserve_all_selected_filters(self, app, client, monkeypatch, scope):
        director_id = _create_user(app, email='filtered-pages@test.com', role='director')
        campuses = {'include': (1, 2), 'exclude': (1, 4), 'legacy': (1, 1)}[scope]
        with app.app_context():
            for index in range(12):
                db.session.add(Event(
                    title=f'Filtered Activity {index}', description='Filter persistence',
                    date=datetime(2026, 10, 20), slots=10, campus_id=campuses[index % 2],
                    category='Environment'))
            for title, campus, date, category in [
                    ('Filtered Activity wrong campus', 3, datetime(2026, 10, 20), 'Environment'),
                    ('Filtered Activity wrong date', 1, datetime(2027, 1, 1), 'Environment'),
                    ('Filtered Activity wrong category', 1, datetime(2026, 10, 20), 'Health'),
                    ('Unrelated name', 1, datetime(2026, 10, 20), 'Environment')]:
                db.session.add(Event(title=title, description='Excluded fixture', date=date,
                                     slots=10, campus_id=campus, category=category))
            db.session.commit()
        _login_as(client, director_id)
        filters = {'start_date': '2026-10-01', 'end_date': '2026-12-31',
                   'campus_id': '1', 'category': 'Environment',
                   'sex': 'prefer_not_to_say', 'start_year': '2020',
                   'end_year': '2025', 'award_year': '2026',
                   'activity_type': 'Outreach', 'department': 'Engineering',
                   'activity_name': 'Filtered Activity', 'page': '1', 'view': 'live'}
        selected = ['2', '3'] if scope == 'exclude' else ['1', '2']
        if scope != 'legacy':
            filters.update(campus=selected, campus_mode=scope)
        body = client.get('/analytics', query_string=filters).get_data(as_text=True)
        document = parse_html(body)
        navigation = document.one('nav', **{'aria-label': 'Live activity report pages'})
        page_link = next(link.attrs['href'] for link in navigation.all('a')
                         if parse_qs(urlsplit(link.attrs['href']).query).get('page') == ['2'])
        live_filters = {key: [value] for key, value in filters.items()
                        if key not in ('start_year', 'end_year', 'activity_type', 'page', 'view', 'campus')}
        live_filters.update(campus=['1'] if scope == 'legacy' else selected,
                            campus_mode=['exclude' if scope == 'exclude' else 'include'])
        assert parse_qs(urlsplit(page_link).query) == {**live_filters, 'view': ['live'], 'page': ['2']}
        second = client.get(page_link)
        assert second.status_code == 200
        second_document = parse_html(second.get_data(as_text=True))
        for page in (document, second_document):
            for link in page.one('nav', **{'aria-label': 'Live activity report pages'}).all('a'):
                query = parse_qs(urlsplit(link.attrs['href']).query)
                assert query.pop('page') in (['1'], ['2'])
                assert query == {**live_filters, 'view': ['live']}
        def titles(page):
            region = page.one('div', **{'aria-label': 'Live activity report table'})
            return [row.all('td')[0].text for row in region.one('tbody').all('tr')]
        expected = [f'Filtered Activity {index}' for index in reversed(range(12))]
        assert titles(document) == expected[:10]
        assert titles(second_document) == expected[10:]
        def pdf(rows, summary, meta):
            assert [row['title'] for row in rows] == expected
            assert summary['event_count'] == 12
            return b'%PDF-filter-scope'
        monkeypatch.setattr('app.routes.director.render_pdf', pdf)
        exports = [link.attrs['href'] for link in document.all('a')
                   if urlsplit(link.attrs.get('href', '')).path in
                   ('/reports/university.csv', '/reports/university.pdf')]
        assert len(exports) == 2
        for link in exports:
            assert parse_qs(urlsplit(link).query) == live_filters
            response = client.get(link)
            assert response.status_code == 200
            if urlsplit(link).path.endswith('.csv'):
                rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
                header = next(index for index, row in enumerate(rows) if row and row[0] == 'Activity')
                assert [row[0] for row in rows[header + 1:] if row and row[0] != 'TOTAL'] == expected
            else:
                assert response.data == b'%PDF-filter-scope'

    def test_admin_accesses_university_analytics(self, app, client):
        aid = _create_user(app, email='admin_an@t.com', role='admin')
        _login_as(client, aid)
        resp = client.get('/analytics')
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'Administration' in body
        assert 'Director Console' not in body

    def test_volunteer_denied_privileged_analytics(self, app, client):
        vid = _create_user(app, email='vol_an@t.com', role='volunteer',
                           campus_id=1)
        _login_as(client, vid)
        assert client.get('/analytics').status_code in (302, 403)
        assert client.get('/coordinator_analytics').status_code in (302, 403)

    # â”€â”€ Aggregations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_monthly_engagement_chronological(self, app):
        e1 = self._event(app, 'Jan', datetime(2020, 1, 15), 5, 'Environment')
        e2 = self._event(app, 'Mar', datetime(2020, 3, 15), 5, 'Environment')
        self._reg(app, user_id=self._vol(app, 'm1@t.com'), event_id=e1,
                  attendance_status='present')
        self._reg(app, user_id=self._vol(app, 'm2@t.com'), event_id=e2,
                  attendance_status='present')
        with app.app_context():
            m = AnalyticsAggregator.monthly_engagement(campus_id=5)
        assert m['months'] == ['2020-01', '2020-03']   # chronological
        assert sum(m['registrations']) == 2

    def test_weekly_engagement_works(self, app):
        e1 = self._event(app, 'W1', datetime(2020, 1, 6), 5, 'Environment')
        e2 = self._event(app, 'W2', datetime(2020, 1, 13), 5, 'Environment')
        self._reg(app, user_id=self._vol(app, 'w1@t.com'), event_id=e1,
                  attendance_status='present')
        self._reg(app, user_id=self._vol(app, 'w2@t.com'), event_id=e2,
                  attendance_status='present')
        with app.app_context():
            w = AnalyticsAggregator.weekly_engagement(campus_id=5)
        assert len(w['weeks']) == 2
        assert sum(w['registrations']) == 2
        assert w['weeks'] == sorted(w['weeks'])

    def test_activity_performance(self, app):
        eid = self._event(app, 'Perf', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        for i in range(3):
            v = self._vol(app, f'p{i}@t.com')
            self._reg(app, user_id=v, event_id=eid, status='completed',
                      attendance_status='present')
        with app.app_context():
            rows = AnalyticsAggregator.activity_performance(campus_id=5)
        assert rows[0]['registrations'] == 3
        assert rows[0]['conversion_rate'] == 100.0

    def test_activity_target_uses_verified_attendance(self, app):
        event_id = self._event(app, 'Target', datetime.now() + timedelta(days=1), 5)
        with app.app_context():
            db.session.get(Event, event_id).target_participants = 4
            db.session.commit()
        self._reg(app, user_id=self._vol(app, 'target-present@test.com'),
                  event_id=event_id, attendance_status='present')
        self._reg(app, user_id=self._vol(app, 'target-absent@test.com'),
                  event_id=event_id, attendance_status='absent')
        with app.app_context():
            row = next(item for item in AnalyticsAggregator.activity_accomplishments(5)
                       if item['event'].id == event_id)
        assert row['actual'] == 1
        assert row['completion_percentage'] == 25.0

    def test_category_distribution(self, app):
        e1 = self._event(app, 'E1', datetime.now() + timedelta(days=1), 5,
                         'Environment')
        e2 = self._event(app, 'E2', datetime.now() + timedelta(days=2), 5,
                         'Health & Wellness')
        self._reg(app, user_id=self._vol(app, 'c1@t.com'), event_id=e1,
                  attendance_status='present')
        self._reg(app, user_id=self._vol(app, 'c2@t.com'), event_id=e2,
                  attendance_status='present')
        with app.app_context():
            cats = AnalyticsAggregator.category_distribution(campus_id=5)
        by = {c['category']: c['registrations'] for c in cats}
        assert by['Environment'] == 1
        assert by['Health & Wellness'] == 1

    def test_campus_comparison(self, app):
        eid = self._event(app, 'Cmp', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        v = self._vol(app, 'cmp@t.com')
        self._reg(app, user_id=v, event_id=eid, status='completed',
                  attendance_status='present')
        with app.app_context():
            cmp = AnalyticsAggregator.campus_comparison()
        bay = next(r for r in cmp if r['campus'] == 'Binmaley')
        assert bay['registrations'] == 1
        assert bay['attended'] == 1

    def test_psu_vs_outsider_classification(self, app):
        eid = self._event(app, 'Ext', datetime.now() + timedelta(days=1), 5,
                          'Environment')
        with app.app_context():
            ext = ExternalParticipant(id_number='EXT-001')
            db.session.add(ext)
            db.session.commit()
            ext_id = ext.id
        self._reg(app, external_id=ext_id, event_id=eid, status='completed',
                  attendance_status='present')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(campus_id=5)
            split = AnalyticsAggregator.psu_vs_outsider(campus_id=5)
        assert s['psu_registrations'] == 0
        assert s['external_registrations'] == 1
        assert s['unique_volunteers'] == 0       # outsiders are not users
        assert split['outsider'] == 1
        assert split['psu'] == 0

    def test_date_filter_works(self, app):
        self._event(app, 'Old', datetime(2020, 1, 1), 5, 'Environment')
        self._event(app, 'New', datetime(2030, 1, 1), 5, 'Environment')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(
                campus_id=5, start_date='2025-01-01')
        # Only the 2030 event is in range (no registrations => 0).
        assert s['event_count'] == 1

    def test_combined_campus_category_filter(self, app):
        self._event(app, 'Env', datetime.now() + timedelta(days=1), 5,
                    'Environment')
        self._event(app, 'Hlth', datetime.now() + timedelta(days=2), 5,
                    'Health & Wellness')
        with app.app_context():
            s = AnalyticsAggregator.participation_summary(
                campus_id=5, category='Environment')
        assert s['event_count'] == 1

    def test_empty_datasets_do_not_crash(self, app):
        # Campus 6 has no seed events and we add none.
        with app.app_context():
            assert AnalyticsAggregator.campus_comparison() is not None
            assert AnalyticsAggregator.category_distribution(campus_id=6) == []
            m = AnalyticsAggregator.monthly_engagement(campus_id=6)
            assert m['months'] == []
            w = AnalyticsAggregator.weekly_engagement(campus_id=6)
            assert w['weeks'] == []
            assert AnalyticsAggregator.skill_distribution() == []
            assert AnalyticsAggregator.interest_distribution() == []
class TestPhaseTwoControls:
    def test_activity_schedule_and_cancellation_deadline(self, client, app):
        coordinator_id = _create_user(
            app, email='phase2coord@test.com', role='coordinator', campus_id=1)
        _login_as(client, coordinator_id)
        response = client.post('/create_activity', data={
            'title': 'Phase 2 Activity',
            'description': 'Tests the complete event schedule.',
            'date': '2030-06-10T09:00',
            'end_date': '2030-06-10T12:00',
            'cancellation_days': 2,
            'category': 'General',
            'slots': 20,
        })

        assert response.status_code == 302
        with app.app_context():
            event = Event.query.filter_by(title='Phase 2 Activity').one()
            assert event.end_date == datetime(2030, 6, 10, 12)
            assert event.cancellation_deadline == datetime(2030, 6, 8, 9)

    def test_announcement_notifies_registered_volunteer(self, client, app):
        coordinator_id = _create_user(
            app, email='announcecoord@test.com', role='coordinator', campus_id=1)
        volunteer_id = _create_user(
            app, email='announcevol@test.com', campus_id=1)
        with app.app_context():
            db.session.add(Registration(
                user_id=volunteer_id, event_id=1, status='confirmed'))
            db.session.commit()
        _login_as(client, coordinator_id)

        response = client.post('/coordinator/events/1/announcements', data={
            'announcement_type': 'event_update',
            'message': 'Meet at the campus gate at 8:30 AM.',
        })

        assert response.status_code == 302
        with app.app_context():
            assert EventAnnouncement.query.filter_by(event_id=1).count() == 1
            assert Notification.query.filter_by(
                user_id=volunteer_id,
                notification_type='event_update',
            ).count() == 1


class TestActivityCalendarViews:
    def test_coordinator_calendar_is_campus_scoped(self, app, client):
        coordinator_id = _create_user(
            app, email='calendar-coordinator@test.com', role='coordinator', campus_id=1)
        _login_as(client, coordinator_id)
        response = client.get('/coordinator/calendar')
        assert response.status_code == 200
        assert 'Activity calendar' in response.get_data(as_text=True)

    def test_director_calendar_requires_director_role(self, app, client):
        volunteer_id = _create_user(app, email='calendar-volunteer@test.com', campus_id=1)
        _login_as(client, volunteer_id)
        assert client.get('/director/calendar').status_code in (302, 403)

    def test_director_calendar_renders_for_director(self, app, client):
        director_id = _create_user(app, email='calendar-director@test.com', role='director')
        _login_as(client, director_id)
        response = client.get('/director/calendar')
        assert response.status_code == 200
        assert 'University activity calendar' in response.get_data(as_text=True)
