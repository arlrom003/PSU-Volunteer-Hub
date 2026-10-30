"""Summary-to-detail navigation must preserve the filtered report evidence."""
from datetime import datetime
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import render_template_string

from app.models import db
from app.models.event import Event
from tests.html_helpers import parse_html
from tests.test_app import app, client, _create_user, _login_as


@pytest.mark.parametrize('role,path', [
    ('director', '/analytics'), ('coordinator', '/coordinator_analytics'),
    ('admin', '/analytics'),
])
def test_analytics_groups_hide_details_but_keep_the_overview(app, client, role, path):
    _login_as(client, _create_user(app, role=role, campus_id=1))
    response = client.get(path)
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    groups = [page.one('details', id=key) for key in (
        'participation-breakdowns', 'detailed-report', 'supporting-insights')]
    for group in groups:
        assert 'open' not in group.attrs
        assert not group.all('details', **{'class': 'secondary-workspace'})
        assert 'Participation Outcomes' not in group.text
        assert 'Apply Filters' not in group.text
        assert 'Export CSV' not in group.text
    assert groups[0].one('div', id='engagementChart')
    assert groups[1].one('section', id='decision-records')
    assert 'How these numbers are counted' not in page.text
    assert 'Attendance Rate' in page.text


@pytest.mark.parametrize('path,query', [
    ('/analytics', '?page=2'), ('/analytics', '?event_id=1'),
    ('/analytics', '?attention=pending_attendance'),
    ('/coordinator_analytics', '?event_id=1'),
    ('/coordinator_analytics', '?attention=pending_attendance'),
])
def test_targeted_report_requests_reveal_the_report(app, client, path, query):
    role = 'coordinator' if path.startswith('/coordinator') else 'director'
    _login_as(client, _create_user(app, role=role, campus_id=1))
    response = client.get(path + query)
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    assert 'open' in page.one('details', id='detailed-report').attrs
    assert 'open' not in page.one('details', id='participation-breakdowns').attrs


def test_director_dashboard_groups_campus_chart_and_matches_its_table(app, client):
    _login_as(client, _create_user(app, role='director', campus_id=1))
    page = parse_html(client.get('/director_dash?period=all').get_data(as_text=True))
    group = page.one('details', id='campus-participation')
    assert 'open' not in group.attrs
    data = json.loads(group.one('script', id='director-campus-chart-data').text)
    table = group.one('table', **{'class': 'data-table campus-chart-values'})
    rows = table.one('tbody').all('tr')
    assert [row.one('th', scope='row').text for row in rows] == data['labels']
    assert [[int(cell.text) for cell in row.all('td')] for row in rows] == list(
        map(list, zip(data['primary'], data['secondary'])))


@pytest.mark.parametrize('primary,secondary', [([], []), ([0], [0]), ([1], [0]), ([3], [3]), ([12000], [11000])])
def test_campus_values_are_readable_without_javascript(app, primary, secondary):
    data = dict(labels=['Long Campus Name'] if primary else [], primary=primary, secondary=secondary)
    with app.test_request_context():
        markup = render_template_string(
            "{% from 'partials/dashboard_ui.html' import chart %}"
            "{{ chart('Campus participation', 'Recorded counts', 'All dates', 'campus', data, 'grouped') }}",
            data=data)
    page = parse_html(markup)
    table = page.one('table', **{'class': 'data-table campus-chart-values'})
    assert [cell.text for cell in table.one('thead').all('th')] == [
        'Campus', 'Registrations', 'Verified Attendance']
    if primary:
        assert [int(cell.text) for cell in table.one('tbody').all('td')] == [primary[0], secondary[0]]
    else:
        assert 'No records match this scope.' in table.text


def test_report_pagination_keeps_scope_and_targets_the_expanded_report(app, client):
    for index in range(12):
        db.session.add(Event(title=f'Grouped report {index}', description='Test record',
                             date=datetime.now(), campus_id=1, category='Environment'))
    db.session.commit()
    _login_as(client, _create_user(app, role='director', campus_id=1))
    page = parse_html(client.get(
        '/analytics?period=all&activity_name=Grouped&campus=1').get_data(as_text=True))
    links = page.one('nav', **{'aria-label': 'Live Activity Report Pages'}).all('a')
    for link in links:
        url = urlsplit(link.attrs['href'])
        query = parse_qs(url.query)
        assert url.fragment == 'decision-records'
        assert query['activity_name'] == ['Grouped'] and query['campus'] == ['1']
