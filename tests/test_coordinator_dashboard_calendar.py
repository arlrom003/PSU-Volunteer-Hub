"""The dashboard calendar shares a campus schedule without changing report scope."""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from app.models import db
from app.models.event import Event
from tests.html_helpers import parse_html
from tests.test_app import app, client, _create_user, _login_as


@pytest.mark.parametrize('path', ['/coordinator_dash?calendar_year=2026&calendar_month=10',
                                  '/coordinator/calendar?year=2026&month=10'])
def test_calendar_shows_the_full_month_for_only_the_coordinators_campus(app, client, path):
    for title, date, campus in [
        ('Earlier campus event', datetime(2026, 10, 2, 9), 1),
        ('Later campus event', datetime(2026, 10, 29, 14), 1),
        ('Same-day campus event', datetime(2026, 10, 29, 16), 1),
        ('Other campus calendar event', datetime(2026, 10, 29, 12), 2),
        ('Outside calendar month', datetime(2026, 11, 2, 9), 1),
    ]:
        db.session.add(Event(title=title, description='Calendar test', date=date,
                             campus_id=campus, category='Environment'))
    db.session.commit()
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    page = parse_html(client.get(path).get_data(as_text=True))
    table = page.one('table', **{'class': 'campus-calendar'})
    assert 'Earlier campus event' in table.text and 'Later campus event' in table.text
    assert 'Same-day campus event' in table.text and '04:00 PM' in table.text
    assert 'Other campus calendar event' not in table.text and 'Outside calendar month' not in table.text
    assert len(table.one('thead').all('th')) == 7
    assert len(table.one('tbody').all('td')) in (28, 35, 42)
    same_day = [cell for cell in table.one('tbody').all('td') if 'Same-day campus event' in cell.text]
    assert len(same_day) == 1 and 'Later campus event' in same_day[0].text
    for link in table.all('a'):
        assert link.attrs['href'].startswith('/coordinator/events/') and link.attrs['href'].endswith('/edit')


def test_calendar_month_links_preserve_dashboard_state_and_roll_years(app, client):
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    page = parse_html(client.get('/coordinator_dash?calendar_year=2026&calendar_month=12'
        '&attention_page=2&period=all&status=completed&category=Environment&goal_year=2026&sample=1'
        '&start_date=2020-01-01&end_date=2030-01-01').get_data(as_text=True))
    nav = page.one('nav', **{'aria-label': 'Calendar Month'})
    next_url = next(link.attrs['href'] for link in nav.all('a') if link.text == 'Next Month')
    query = parse_qs(urlsplit(next_url).query)
    assert query['calendar_year'] == ['2027'] and query['calendar_month'] == ['1']
    assert query['attention_page'] == ['2'] and query['period'] == ['all']
    assert query['status'] == ['completed'] and query['category'] == ['Environment']
    assert query['goal_year'] == ['2026'] and query['sample'] == ['1']
    assert query['start_date'] == ['2020-01-01'] and query['end_date'] == ['2030-01-01']
    assert urlsplit(next_url).fragment == 'activity-calendar'
    january = parse_html(client.get(next_url).get_data(as_text=True))
    previous = next(link.attrs['href'] for link in january.one('nav', **{'aria-label': 'Calendar Month'}).all('a')
                    if link.text == 'Previous Month')
    assert parse_qs(urlsplit(previous).query)['calendar_month'] == ['12']


@pytest.mark.parametrize('scope', ['calendar_year=2000&calendar_month=1',
                                  'calendar_year=10000&calendar_month=99',
                                  'calendar_year=invalid&calendar_month=invalid',
                                  'calendar_year=1&calendar_month=1',
                                  'calendar_year=9999&calendar_month=12'])
def test_empty_and_invalid_calendar_months_remain_usable(app, client, scope):
    _login_as(client, _create_user(app, role='coordinator', campus_id=1))
    response = client.get('/coordinator_dash?' + scope)
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    assert page.one('table', **{'class': 'campus-calendar'})
    workspace = page.one('section', id='activity-workspace')
    assert 'Manage Activities' in workspace.text and workspace.one('select', name='status')
    assert not page.all('details', id='activity-workspace')
    assert not any(heading.text == 'Upcoming Activities' for heading in page.all('h2'))
    if scope.startswith('calendar_year=2000'):
        assert 'No activities are scheduled this month' in page.text
