"""Public browsing and volunteer-only joining use isolated SQLite fixtures."""
from datetime import datetime, timedelta
from html import unescape
import re
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.test_app import app, client, _create_user, _login_as
from app.models import db
from app.models.event import Event, Registration, SdgGoal
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.user import User


def login(app, client, role='volunteer'):
    uid = _create_user(app, role=role, campus_id=1)
    _login_as(client, uid)
    return uid


def test_public_details_are_read_only_and_do_not_disclose_consent_bodies(app, client):
    event = db.session.get(Event, 1)
    event.participation_agreement_text = 'PRIVATE-AGREEMENT-MARKER'
    event.nda_required = True
    event.nda_text = 'PRIVATE-NDA-MARKER'
    goal = SdgGoal(number=4, name='Quality education')
    event.sdgs.append(goal)
    db.session.commit()
    counts = [model.query.count() for model in (Registration, AuditLog, Notification)]
    response = client.get('/opportunities/1')
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert event.title in body and 'Quality education' in body
    assert 'Sign in to join' in body
    assert 'PRIVATE-AGREEMENT-MARKER' not in body and 'PRIVATE-NDA-MARKER' not in body
    assert counts == [model.query.count() for model in (Registration, AuditLog, Notification)]
    assert client.get('/opportunities/999999').status_code == 404
    assert client.post('/opportunities/1').status_code == 405


@pytest.mark.parametrize('role', ['volunteer', 'coordinator', 'director', 'admin'])
def test_role_details_and_join_authorization(app, client, role):
    login(app, client, role)
    response = client.get('/opportunities/1')
    assert response.status_code == 200
    assert f'role-page--{role}' in response.get_data(as_text=True)
    if role == 'volunteer':
        assert b'>Join Now</a>' in response.data
    else:
        assert b'Volunteer accounts can join activities' in response.data
        assert client.get('/opportunities/register/1').status_code == 403
        assert client.post('/opportunities/register/1').status_code == 403


@pytest.mark.parametrize('state', ['full', 'closed', 'registered'])
@pytest.mark.parametrize('method', ['get', 'post'])
def test_unavailable_review_redirects_to_details_without_writes(app, client, state, method):
    uid = login(app, client)
    event = db.session.get(Event, 1)
    if state == 'closed':
        event.date = datetime.now() - timedelta(seconds=1)
    else:
        owner = uid if state == 'registered' else _create_user(app, email='other@example.test')
        db.session.add(Registration(user_id=owner, event_id=1, status='confirmed'))
        if state == 'full': event.slots = 1
    db.session.commit()
    count = Registration.query.count()
    response = getattr(client, method)('/opportunities/register/1?search=help', data={'accept_agreement': 'yes'})
    assert response.status_code == 302
    assert response.location == '/opportunities/1?search=help'
    body = client.get(response.location).get_data(as_text=True)
    assert {'full': 'Full', 'closed': 'Registration closed', 'registered': 'My registrations'}[state] in body
    assert Registration.query.count() == count


def test_list_filters_back_links_and_sign_in_return_are_whitelisted(app, client):
    query = 'search=Coding&category=Education+%26+Literacy&campus=1&campus=2&campus_mode=exclude&page=1&return_to=https://bad.example&next=//bad.example'
    body = client.get('/opportunities/1?' + query).get_data(as_text=True)
    back = unescape(re.search(r'href="([^"]+)"[^>]*>Back to opportunities', body)[1])
    assert urlsplit(back).path == '/opportunities'
    args = parse_qs(urlsplit(back).query)
    assert args['campus'] == ['1', '2'] and args['campus_mode'] == ['exclude']
    assert 'return_to' not in args and 'next' not in args
    sign_in = unescape(re.search(r'href="([^"]+)"[^>]*>Sign in to join', body)[1])
    target = parse_qs(urlsplit(sign_in).query)['next'][0]
    assert urlsplit(target).path == '/opportunities/register/1'
    assert parse_qs(urlsplit(target).query) == args
    _create_user(app)
    with app.app_context():
        response = client.post(sign_in, data={'identifier': 'test@example.com', 'password': 'password123'})
    assert response.location == target
    with app.app_context():
        consent = client.get(target)
    actions = re.findall(r'<form method="post" action="([^"]+)"', consent.get_data(as_text=True))
    assert target in [unescape(action) for action in actions]


@pytest.mark.parametrize('restore', [False, True])
def test_join_confirmation_is_database_backed_and_refresh_safe(app, client, restore):
    uid = login(app, client)
    event = db.session.get(Event, 1)
    event.participation_agreement_text = 'QA participation text'
    event.participation_agreement_version = 'qa-v1'
    if restore:
        db.session.add(Registration(user_id=uid, event_id=1, status='cancelled'))
    db.session.commit()
    response = client.post('/opportunities/register/1?search=Coding&campus=1', data={'accept_agreement': 'yes'})
    assert response.location == '/opportunities/1?search=Coding&campus=1'
    body = client.get(response.location).get_data(as_text=True)
    assert ('restored for' if restore else 'You have joined') in body
    assert event.title in body and 'My registrations' in body
    assert '>Join Now</a>' not in body
    record = Registration.query.filter_by(user_id=uid, event_id=1).one()
    assert record.status == 'confirmed' and record.policy_version == 'qa-v1'
    assert record.policy_accepted_at is not None
    before = (Registration.query.count(), AuditLog.query.count())
    client.get(response.location)
    client.post('/opportunities/register/1', data={'accept_agreement': 'yes'})
    assert before == (Registration.query.count(), AuditLog.query.count())


def test_consent_validation_preserves_only_submitted_choices(app, client):
    login(app, client)
    event = db.session.get(Event, 1)
    event.nda_required, event.nda_text, event.nda_version = True, 'QA NDA text', 'nda-qa'
    db.session.commit()
    initial = client.get('/opportunities/register/1').get_data(as_text=True)
    assert not re.search(r'<input[^>]*name="accept_[^"]+"[^>]* checked', initial)
    response = client.post('/opportunities/register/1', data={'accept_agreement': 'yes'})
    body = response.get_data(as_text=True)
    assert response.status_code == 400 and 'data-consent-errors' in body
    assert re.search(r'<input[^>]*name="accept_agreement"[^>]* checked', body)
    assert re.search(r'<input[^>]*name="accept_nda"[^>]*aria-invalid="true"', body)
    assert 'accept_nda-error' in body and 'registration-consent.js' in body
    assert Registration.query.count() == 0
    response = client.post('/opportunities/register/1', data={'accept_agreement': 'yes', 'accept_nda': 'yes'})
    assert response.status_code == 302
    record = Registration.query.one()
    assert record.nda_version == 'nda-qa' and record.nda_accepted_at is not None


def test_stale_availability_and_expired_session_cannot_join(app, client):
    uid = login(app, client)
    assert client.get('/opportunities/register/1').status_code == 200
    other = _create_user(app, email='last-slot@example.test')
    db.session.get(Event, 1).slots = 1
    db.session.add(Registration(user_id=other, event_id=1, status='confirmed'))
    db.session.commit()
    assert client.post('/opportunities/register/1', data={'accept_agreement': 'yes'}).location == '/opportunities/1'
    assert Registration.query.filter_by(user_id=uid).count() == 0
    with client.session_transaction() as session:
        session['last_activity_at'] = time.time() - 1801
    response = client.post('/opportunities/register/2', data={'accept_agreement': 'yes'})
    assert response.location.endswith('/auth/login')
    assert Registration.query.filter_by(user_id=uid).count() == 0


def test_details_missing_long_and_escaped_content_and_zero_capacity(app, client):
    event = db.session.get(Event, 1)
    event.description = '<script>alert(1)</script>' + 'LongContent' * 100
    event.location, event.end_date, event.slots = '', None, 0
    event.required_skills_rel = []
    db.session.commit()
    body = client.get('/opportunities/1').get_data(as_text=True)
    for text in ['&lt;script&gt;', 'End time not provided', 'Location not provided',
                 'No specific skills listed', 'No SDGs listed', 'Capacity not specified']:
        assert text in body
    assert '<script>alert(1)</script>' not in body and 'No slots are currently available' not in body
    with app.app_context():
        authenticated = app.test_client()
        _login_as(authenticated, _create_user(app))
        assert authenticated.post('/opportunities/register/1', data={'accept_agreement': 'yes'}).status_code == 302
    assert Registration.query.filter_by(event_id=1).one().status == 'confirmed'


def test_listing_status_text_counts_and_empty_states(app, client):
    body = client.get('/opportunities?search=Coding&campus=1').get_data(as_text=True)
    assert 'Applied filters' in body and 'Search: Coding' in body and 'Campuses: Lingayen' in body
    assert 'Showing 1–1 of 1 opportunity' in body
    assert 'View details' in body and 'Cancel by' not in body
    assert b'No opportunities match these filters.' in client.get('/opportunities?search=not-found').data
    padded = client.get('/opportunities?search=%20Coding%20').get_data(as_text=True)
    assert 'Search: Coding' in padded and 'Showing 1–1 of 1 opportunity' in padded
    for event in Event.query.all(): event.date = datetime.now() - timedelta(days=1)
    db.session.commit()
    assert b'No upcoming activities' in client.get('/opportunities').data


def test_stale_page_has_truthful_count_and_first_page_recovery(client):
    response = client.get('/opportunities?page=999&campus=1')
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Showing 0 of 4 opportunities' in body and 'No activities on this page' in body
    first = unescape(re.search(r'href="([^"]+)"[^>]*>First page', body)[1])
    assert parse_qs(urlsplit(first).query) == {'page': ['1'], 'campus': ['1']}
