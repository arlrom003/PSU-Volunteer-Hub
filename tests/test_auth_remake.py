"""Authentication UI and form-state regressions using isolated SQLite fixtures."""
from html.parser import HTMLParser
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_app import app, client, _create_user, _login_as
from app.models import db
from app.models.user import (User, Interest, Skill, SystemSetting, VolunteerProfile,
                             PasswordResetToken)
from app.models.policy import (TermsRevision, PrivacyRevision, TermsAcceptance,
                               PrivacyAcknowledgement)


class Tags(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, name, attrs):
        self.tags.append((name, dict(attrs)))

    def named(self, name):
        return next(attrs for tag, attrs in self.tags if attrs.get('name') == name)


@pytest.fixture
def catalog(app):
    with app.app_context():
        interest = Interest(name='Education & Literacy')
        skill = Skill(name='Teaching/Tutoring')
        db.session.add_all([interest, skill])
        db.session.commit()
        return str(interest.id), str(skill.id)


def signup_data(**overrides):
    return dict(first_name='QA', last_name='Volunteer', email='signup-ui@example.test',
                password='12345678', password_confirmation='12345678',
                volunteer_type='student', sex='prefer_not_to_say',
                id_number='AUTH-QA-01', college_affiliation='QA College',
                campus='1', **overrides)


@pytest.mark.parametrize('path', ['/auth/login', '/auth/interests', '/auth/register'])
def test_primary_pages_use_shared_accessible_shell(client, path):
    response = client.get(path)
    body = response.get_data(as_text=True)
    tags = Tags(body)
    assert response.status_code == 200
    assert len([1 for tag, _ in tags.tags if tag == 'h1']) == 1
    logo = next(attrs for tag, attrs in tags.tags
                if tag == 'img' and attrs.get('width') == '128')
    assert logo['width'] == logo['height'] == '128'
    assert '/static/assets/PSU-logo.png' in logo['src']
    assert 'id="main-content"' in body
    assert 'href="#main-content"' in body
    assert 'aria-label="Account navigation"' in body
    assert '/static/scripts/auth-forms.js' in body
    assert 'name="remember"' not in body
    assert 'Contains a letter' not in body
    assert 'Contains a number' not in body


def test_failed_login_preserves_escaped_identifier_but_not_password(client):
    body = client.post('/auth/login', data={
        'identifier': 'qa"<account>@example.test', 'password': 'NeverEchoThis123!'
    }).get_data(as_text=True)
    tags = Tags(body)
    assert tags.named('identifier')['value'] == 'qa"<account>@example.test'
    assert tags.named('identifier')['aria-describedby'] == 'login-error'
    assert tags.named('password').get('value', '') == ''
    assert 'NeverEchoThis123!' not in body
    assert 'Invalid email/ID or password.' in body
    assert 'data-error-summary' in body


@pytest.mark.parametrize('data, message', [
    ({}, 'Select at least one interest.'),
    ({'interests': '1'}, 'Select at least one skill.'),
    ({'interests': '999', 'skills': '999'}, 'Select at least one interest.'),
])
def test_preferences_validate_before_advancing(client, catalog, data, message):
    response = client.post('/auth/interests', data=data)
    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    assert 'data-error-summary' in response.get_data(as_text=True)


def test_preferences_restore_on_return_and_survive_account_errors(client, catalog):
    interest, skill = catalog
    response = client.post('/auth/interests', data={'interests': interest, 'skills': skill})
    assert response.status_code == 302
    assert response.location == '/auth/register'
    assert client.post('/auth/register', data={}).status_code == 200
    markup = client.get('/auth/interests').get_data(as_text=True)
    inputs = {attrs['id']: attrs for tag, attrs in Tags(markup).tags if tag == 'input' and 'id' in attrs}
    assert 'checked' in inputs[f'interest-{interest}']
    assert 'checked' in inputs[f'skill-{interest}-{skill}']


def test_empty_catalog_does_not_add_a_new_registration_requirement(client):
    response = client.get('/auth/interests')
    assert b'No interests are configured.' in response.data
    assert client.post('/auth/interests', data={}).status_code == 302


def test_signup_errors_are_linked_and_retain_non_password_values(client, app):
    with app.app_context():
        db.session.add(SystemSetting(key='default_password_length', value='12'))
        db.session.commit()
    data = signup_data()
    data.update(password='Short123!', password_confirmation='Different123!', sex='invalid')
    body = client.post('/auth/register', data=data).get_data(as_text=True)
    tags = Tags(body)
    assert tags.named('first_name')['value'] == 'QA'
    assert tags.named('email')['value'] == data['email']
    assert tags.named('id_number')['value'] == 'AUTH-QA-01'
    assert tags.named('password')['aria-invalid'] == 'true'
    assert 'password-error' in tags.named('password')['aria-describedby']
    assert tags.named('password')['minlength'] == '12'
    assert 'href="#password"' in body
    assert 'href="#password_confirmation"' in body
    assert 'href="#sex"' in body
    assert 'Use at least 12 characters.' in body
    assert 'Short123!' not in body and 'Different123!' not in body
    assert 'data-warn-unsaved' in body
    with client.session_transaction() as saved_session:
        assert 'first_name' not in saved_session and 'password' not in saved_session


def test_signup_missing_preferences_links_back_to_step_one(client, catalog):
    response = client.post('/auth/register', data=signup_data())
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/auth/interests">Select at least one interest.' in body
    assert 'href="/auth/interests">Select at least one skill.' in body


def test_signup_displays_real_policy_text_and_does_not_preselect_consent(client, app):
    with app.app_context():
        db.session.add(TermsRevision(title='QA Terms', body='QA terms body <script>unsafe</script>', version='1'))
        db.session.add(PrivacyRevision(title='QA Privacy', body='QA privacy body', version='1'))
        db.session.commit()
    for response in [client.get('/auth/register'), client.post('/auth/register', data={})]:
        body = response.get_data(as_text=True)
        tags = Tags(body)
        assert 'QA terms body &lt;script&gt;unsafe&lt;/script&gt;' in body
        assert 'QA privacy body' in body
        assert len([1 for tag, _ in tags.tags if tag == 'details']) == 2
        assert 'checked' not in tags.named('terms_accepted')
        assert 'checked' not in tags.named('privacy_acknowledged')


def test_signup_preserves_existing_password_policy_and_records_consents(client, app, catalog):
    with app.app_context():
        db.session.add(TermsRevision(title='QA Terms', body='Test terms.', version='1'))
        db.session.add(PrivacyRevision(title='QA Privacy', body='Test notice.', version='1'))
        db.session.commit()
    interest, skill = catalog
    client.post('/auth/interests', data={'interests': interest, 'skills': skill})
    data = signup_data()
    data.update(terms_accepted='on', privacy_acknowledged='on', account_type='admin')
    response = client.post('/auth/register', data=data)
    assert response.status_code == 302
    assert response.location == '/auth/login'
    with app.app_context():
        user = User.query.filter_by(email=data['email']).one()
        assert user.role == 'volunteer'
        assert user.check_password('12345678')
        assert {str(item.id) for item in user.interests} == {interest}
        assert {str(item.id) for item in user.skills} == {skill}
        assert VolunteerProfile.query.filter_by(user_id=user.id).count() == 1
        assert TermsAcceptance.query.filter_by(user_id=user.id).count() == 1
        assert PrivacyAcknowledgement.query.filter_by(user_id=user.id).count() == 1
    with client.session_transaction() as saved_session:
        assert 'selected_interests' not in saved_session
        assert 'selected_skills' not in saved_session


def test_privacy_acceptance_renders_in_shared_layout(client, app):
    uid = _create_user(app, sex=None)
    raw_token = 'auth-ui-recovery-smoke-token'
    with app.app_context():
        db.session.add(PrivacyRevision(title='Current QA Privacy', body='Visible privacy body.', version='1'))
        db.session.add(PasswordResetToken(
            user_id=uid, token_hash=sha256(raw_token.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(minutes=15)))
        db.session.commit()
    _login_as(client, uid)
    body = client.get('/auth/privacy').get_data(as_text=True)
    assert 'Current QA Privacy' in body
    assert 'Visible privacy body.' in body
    assert 'name="acknowledge_privacy"' in body
    assert 'id="main-content"' in body
    profile = client.get('/auth/complete-sex')
    assert profile.status_code == 200
    assert b'Complete your profile' in profile.data
    assert b'id="main-content"' in profile.data
    # The fixture holds an app context; give the anonymous browser a fresh g.
    with app.app_context():
        recovery = app.test_client().get(f'/auth/reset-password/{raw_token}')
    assert recovery.status_code == 200
    assert b'autocomplete="new-password"' in recovery.data
    assert b'class="input"' in recovery.data
    assert b'id="main-content"' in recovery.data


def test_deactivated_login_uses_native_dialog(client, app):
    uid = _create_user(app, email='inactive-ui@example.test')
    with app.app_context():
        db.session.get(User, uid).is_active = False
        db.session.commit()
    body = client.post('/auth/login', data={
        'identifier': 'inactive-ui@example.test', 'password': 'password123'
    }).get_data(as_text=True)
    assert '<dialog class="auth-modal"' in body
    assert 'data-auto-open' in body
    assert 'aria-describedby="reactivation-description"' in body
    assert 'action="/auth/request-reactivation"' in body


def test_login_has_server_rendered_csrf_field(client, app):
    app.config['WTF_CSRF_ENABLED'] = True
    markup = client.get('/auth/login').get_data(as_text=True)
    token = Tags(markup).named('csrf_token')['value']
    response = client.post('/auth/login', data={
        'identifier': 'no-account@example.test', 'password': 'invalid', 'csrf_token': token})
    assert response.status_code == 200
    assert b'Invalid email/ID or password.' in response.data


def test_auth_script_behaviors():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the JavaScript regression checks')
    result = subprocess.run(
        [node, '--test', str(Path(__file__).with_name('auth-forms.test.cjs'))],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
