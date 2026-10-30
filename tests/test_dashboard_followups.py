"""Dashboard follow-up pages and coverage must retain their distinct scopes."""
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import template_rendered

from app.models import db
from app.models.event import Campus, Event, ExternalParticipant, Registration, CancellationRequest
from tests.html_helpers import parse_html, form_with_control, form_values
from tests.test_app import app, client, _create_user, _login_as


def pending_activities(count, campus_id=1):
    ids = []
    for number in range(count):
        event = Event(title=f'Pending campus {campus_id} activity {number}', description='Follow-up test',
                      campus_id=campus_id, date=datetime.now() - timedelta(days=3, minutes=number))
        participant = ExternalParticipant(id_number=f'page-{campus_id}-{number}', name='Test participant')
        db.session.add_all([event, participant])
        db.session.flush()
        db.session.add(Registration(event_id=event.id, external_participant_id=participant.id, status='confirmed'))
        ids.append(event.id)
    db.session.commit()
    return ids


@pytest.mark.parametrize('count', [0, 1, 5, 6, 15])
def test_coordinator_pages_cover_each_followup_once(app, client, count):
    ids = pending_activities(count)
    pending_activities(2, campus_id=2)
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    seen = []
    for number in range(1, max(1, (count + 4) // 5) + 1):
        response = client.get(f'/coordinator_dash?attention_page={number}')
        assert response.status_code == 200
        page = parse_html(response.get_data(as_text=True))
        rows = [row for row in page.all('li') if 'data-attention-event' in row.attrs]
        page_ids = [int(row.attrs['data-attention-event']) for row in rows]
        assert len(page_ids) == min(5, max(0, count - (number - 1) * 5))
        seen.extend(page_ids)
        assert not page.all('details', **{'class': 'attention-more'})
        if count:
            assert f'Showing {(number - 1) * 5 + 1}–{min(number * 5, count)} of {count}' in page.text
        else:
            assert 'No activities need follow-up' in page.text
        assert bool(page.all('nav', **{'aria-label': 'Needs attention pages'})) == (count > 5)
    assert set(seen) == set(ids) and len(seen) == len(set(seen))


@pytest.mark.parametrize('value,expected', [('invalid', 1), ('0', 1), ('-2', 1), ('999', 3)])
def test_coordinator_page_validation_preserves_dashboard_filters(app, client, value, expected):
    pending_activities(15)
    upcoming = Event.query.filter(Event.date > datetime.now(), Event.campus_id == 1).first()
    participant = ExternalParticipant(id_number='cancellation-page', name='Test participant')
    db.session.add(participant)
    db.session.flush()
    registration = Registration(event_id=upcoming.id, external_participant_id=participant.id, status='confirmed')
    db.session.add(registration)
    db.session.flush()
    db.session.add(CancellationRequest(registration_id=registration.id, reason='Test reason'))
    db.session.commit()
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    query = f'?attention_page={value}&period=all&workspace=1&status=all&category=Environment&start_date=2020-01-01&goal_year=2026'
    page = parse_html(client.get('/coordinator_dash' + query).get_data(as_text=True))
    navigation = page.one('nav', **{'aria-label': 'Needs attention pages'})
    assert navigation.one('a', **{'aria-current': 'page'}).text == f'Page {expected}'
    assert '1 request awaits review' in page.text
    for link in navigation.all('a'):
        url = urlsplit(link.attrs['href'])
        scope = parse_qs(url.query)
        assert url.fragment == 'findings-title'
        assert scope['period'] == ['all'] and scope['category'] == ['Environment']
        assert scope['workspace'] == ['1'] and scope['status'] == ['all']
        assert scope['start_date'] == ['2020-01-01'] and scope['goal_year'] == ['2026']
        assert 'page' not in scope


@pytest.mark.parametrize('role,path', [('director', '/director_dash'), ('coordinator', '/coordinator_dash')])
def test_dashboard_period_and_metrics_share_one_overview(app, client, role, path):
    _login_as(client, _create_user(app, role=role, campus_id=1))
    page = parse_html(client.get(path + '?period=all').get_data(as_text=True))
    overview = page.one('section', **{'class': 'performance-overview'})
    assert overview.one('h2').text == 'Performance overview'
    assert overview.one('select', name='period')
    assert overview.one('button', type='submit').text == 'Apply period'
    assert overview.one('div', **{'class': 'summary-strip'})
    assert 'Participation outcomes' not in overview.text
    assert 'All dates' in overview.text


def test_coordinator_period_submit_keeps_workspace_dates_independent(app, client):
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    page = parse_html(client.get(
        '/coordinator_dash?workspace=1&status=all&start_date=2000-01-01&end_date=2000-01-31&attention_page=2'
    ).get_data(as_text=True))
    values = form_values(form_with_control(page.one('section', **{'class': 'performance-overview'}), 'period'))
    values['period'] = ['all']
    assert 'attention_page' not in values
    response = client.get('/coordinator_dash', query_string=[(key, value) for key, values_ in values.items() for value in values_])
    result = parse_html(response.get_data(as_text=True))
    assert 'selected' in result.one('section', **{'class': 'performance-overview'}).one('select', name='period').one('option', value='all').attrs
    assert result.one('input', name='start_date', type='date').attrs['value'] == '2000-01-01'
    assert result.one('input', name='end_date', type='date').attrs['value'] == '2000-01-31'


@pytest.mark.parametrize('scenario', ['none', 'partial', 'full', 'unassigned', 'no_campuses'])
def test_director_coverage_counts_campuses_in_the_selected_period(app, client, scenario):
    query = '?period=all'
    if scenario == 'none':
        query = '?start_date=2000-01-01&end_date=2000-01-31'
    if scenario == 'full':
        for campus in Campus.query.all():
            db.session.add(Event(title='Campus coverage', description='Test record', date=datetime.now(), campus_id=campus.id))
    if scenario == 'no_campuses':
        Event.query.delete()
        Campus.query.delete()
    if scenario in ('unassigned', 'no_campuses'):
        db.session.add(Event(title='Unassigned activity', description='Test record', date=datetime.now()))
    db.session.commit()
    _login_as(client, _create_user(app, role='director'))
    contexts = []
    def capture(sender, template, context, **extra):
        contexts.append(context)
    with template_rendered.connected_to(capture, app):
        response = client.get('/director_dash' + query)
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    coverage = contexts[-1]['campus_coverage']
    assert 'Needs attention' not in page.text
    assert coverage['total'] == (0 if scenario == 'no_campuses' else 9)
    assert coverage['with_activity'] + coverage['without_activity'] == coverage['total']
    assert len(page.all('a', **{'class': 'campus-coverage__tile'})) == coverage['with_activity']
    assert len(page.all('a', **{'class': 'campus-coverage__tile campus-coverage__tile--empty'})) == coverage['without_activity']
    expected = {'none': 0, 'partial': 6, 'full': 9, 'unassigned': 6, 'no_campuses': 0}
    assert coverage['with_activity'] == expected[scenario]
    assigned_total = sum(campus['activities'] for campus in coverage['campuses'])
    assert contexts[-1]['performance']['activities'] == assigned_total + (scenario in ('unassigned', 'no_campuses'))
    for link in page.all('a'):
        if 'campus-coverage__tile' not in link.attrs.get('class', ''):
            continue
        url = urlsplit(link.attrs['href'])
        assert url.fragment == 'decision-records'
        assert parse_qs(url.query)['campus_mode'] == ['include']
    if scenario == 'no_campuses':
        assert 'No campuses are configured' in page.text
    else:
        assert page.one('div', **{'class': 'campus-coverage__bar'}).attrs['role'] == 'img'
