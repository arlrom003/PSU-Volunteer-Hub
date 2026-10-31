"""Dashboard controls and independently scoped evidence must stay in agreement."""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import template_rendered

from app.annual_goals import campus_ranking
from app.models import db
from app.models.event import Event, Registration, Attendance, Campus
from app.recommendation.analytics import AnalyticsAggregator
from tests.html_helpers import parse_html, form_with_control, form_values
from tests.test_app import app, client, _create_user, _login_as
from tests.test_campus_ranking import campus


def rendered(app, client, url):
    contexts = []
    def capture(sender, template, context, **extra):
        contexts.append(context)
    with template_rendered.connected_to(capture, app):
        response = client.get(url)
    return response, parse_html(response.get_data(as_text=True)), contexts[-1]


@pytest.mark.parametrize('rows,leaders', [
    ([], []), ([campus('No targets', 0, 0)], []),
    ([campus('Zero', 0, 3), campus('Achieved', 1, 3, 2)], ['Zero']),
    ([campus('Zulu', 0, 2), campus('Alpha', 0, 4, 2)], ['Alpha', 'Zulu']),
    ([campus('Zulu', 1, 2), campus('Alpha', 2, 4, 2)], ['Alpha', 'Zulu']),
    ([campus('Lower', 2, 3), campus('Rounded higher', 667, 1000, 2)], ['Lower']),
    ([campus('Zulu', 1, 1), campus('Alpha', 2, 2, 2)], ['Alpha', 'Zulu']),
])
def test_lowest_achievement_preserves_exact_ties_and_zero(rows, leaders):
    result = campus_ranking(rows, lowest=True)
    assert [row['campus'] for row in result['leaders']] == leaders
    assert result['state'] == ('ranked' if leaders else 'unavailable')
    assert all(row['total'] > 0 for row in result['rows'])


@pytest.mark.parametrize('role', ['director', 'admin'])
def test_director_move_preserves_admin_analytics_and_campus_evidence(app, client, role):
    _login_as(client, _create_user(app, role=role))
    _, dashboard, _ = rendered(app, client, '/director_dash?period=all')
    assert dashboard.one('section', id='cross-campus-comparison').one('section', id='filters')
    assert not dashboard.all('details', id='campus-participation')
    assert not dashboard.all('div', **{'data-chart': 'grouped'})
    _, analytics, _ = rendered(app, client, '/analytics?period=all')
    assert analytics.one('div', id='campusComparison')
    assert analytics.one('section', id='campus-outcomes')
    assert not analytics.all('select', name='award_year')
    if role == 'director':
        assert analytics.one('section', id='filters').one('h2').text == 'Selected Report Scope'
        link = next(link for link in analytics.all('a') if link.text == 'Change Filters')
        assert urlsplit(link.attrs['href']).path == '/director_dash'
        assert urlsplit(link.attrs['href']).fragment == 'cross-campus-comparison'
        assert not analytics.all('form', id='analytics-filters')
    else:
        assert analytics.one('form', id='analytics-filters')
        assert 'Filters and Reports' in analytics.one('section', id='filters').text


@pytest.mark.parametrize('role,path', [('director', '/director_dash'), ('coordinator', '/coordinator_dash')])
def test_dashboard_sample_preview_buttons_are_removed(app, client, role, path):
    _login_as(client, _create_user(app, role=role, campus_id=1))
    page = parse_html(client.get(path).get_data(as_text=True))
    assert not any(link.text == 'Preview Sample Data' for link in page.all('a'))
    assert page.one('section', **{'class': 'goal-overview'}).one('button').text == 'Apply Year'


def test_recognition_uses_award_year_independently_and_leaves_analytics(app, client, monkeypatch):
    volunteer = _create_user(app, role='volunteer', email='recognized@test.example')
    event = Event(title='Recognition source', description='Known award evidence',
                  campus_id=1, date=datetime(2024, 7, 10))
    db.session.add(event)
    db.session.flush()
    registration = Registration(event_id=event.id, user_id=volunteer, status='completed')
    db.session.add(registration)
    db.session.flush()
    db.session.add(Attendance(event_id=event.id, registration_id=registration.id,
                              user_id=volunteer, status='present'))
    db.session.commit()
    expected = AnalyticsAggregator.award_leaderboards(2024)
    _login_as(client, _create_user(app, role='director', email='recognition-director@test.example'))
    query = '/director_dash?award_year=2024&goal_year=2026&calendar_year=2025&calendar_month=12'
    _, page, context = rendered(app, client, query + '&campus=2&activity_name=NoMatch&period=all')
    assert context['leaderboards'] == expected
    assert context['performance']['activities'] == 0
    values = form_values(form_with_control(page, 'award_year', tags=('select',)))
    assert values['calendar_month'] == ['12'] and values['campus'] == ['2']
    assert values['goal_year'] == ['2026'] and values['activity_name'] == ['NoMatch']
    assert page.one('section', id='recognition').one('h2', id='recognition-title').text == 'Outstanding Recognition'
    monkeypatch.setattr(AnalyticsAggregator, 'award_leaderboards',
                        lambda year: pytest.fail('Analytics must not calculate recognition'))
    assert client.get('/analytics?period=all').status_code == 200


@pytest.mark.parametrize('query,month', [
    ('calendar_year=2032&calendar_month=12', 'December 2032'),
    ('calendar_year=2033&calendar_month=1', 'January 2033'),
    ('calendar_year=2000&calendar_month=1', 'January 2000'),
    ('calendar_year=1&calendar_month=1', datetime(1, 1, 1).strftime('%B %Y')),
    ('calendar_year=9999&calendar_month=12', 'December 9999'),
    ('calendar_year=invalid&calendar_month=99', datetime.now().strftime('%B %Y')),
])
def test_university_calendar_is_independent_and_month_links_keep_state(app, client, query, month):
    for title, campus_id, day in [('Earlier university event', 1, 2),
                                  ('Later university event', 2, 28),
                                  ('Same-day university event', 1, 28)]:
        db.session.add(Event(title=title, description='Calendar scope', campus_id=campus_id,
                             category='Health', date=datetime(2032, 12, day, 10)))
    db.session.commit()
    _login_as(client, _create_user(app, role='director'))
    _, page, context = rendered(app, client, '/director_dash?' + query +
        '&campus=3&category=Environment&activity_name=NoMatch&award_year=2026&goal_year=2026'
        '&start_date=2020-01-01&end_date=2020-01-31')
    assert context['calendar_month'] == month
    calendar = page.one('section', id='activity-calendar')
    assert len(calendar.one('thead').all('th')) == 7
    assert context['performance']['activities'] == 0
    if month == 'December 2032':
        assert all(title in calendar.text for title in ['Earlier university event', 'Later university event', 'Same-day university event'])
        for link in calendar.one('tbody').all('a'):
            target = parse_qs(urlsplit(link.attrs['href']).query)
            assert target['event_id'] and target['start_date'][0].startswith('2032-12-')
            assert urlsplit(link.attrs['href']).fragment == 'decision-records'
        standalone = parse_html(client.get(
            '/director/calendar?year=2032&month=12&campus_id=1&category=Health').get_data(as_text=True))
        schedule = standalone.one('table', **{'class': 'campus-calendar'})
        assert 'Earlier university event' in schedule.text and 'Same-day university event' in schedule.text
        assert 'Later university event' not in schedule.text
        next_month = next(link for link in standalone.one('nav', **{'aria-label': 'Calendar Month'}).all('a') if link.text == 'Next Month')
        scope = parse_qs(urlsplit(next_month.attrs['href']).query)
        assert scope['year'] == ['2033'] and scope['month'] == ['1']
        assert scope['campus_id'] == ['1'] and scope['category'] == ['Health']
    for link in calendar.one('nav').all('a'):
        target = parse_qs(urlsplit(link.attrs['href']).query)
        assert target['campus'] == ['3'] and target['category'] == ['Environment']
        assert target['award_year'] == ['2026'] and target['goal_year'] == ['2026']
        assert target['start_date'] == ['2020-01-01']
    if 'calendar_year=1&' in query:
        assert len(calendar.one('nav').all('a')) == 1


@pytest.mark.parametrize('mode,selected,expected', [('include', [1], 1), ('exclude', [1], 8),
                                                  ('exclude', list(range(1, 10)), 0)])
def test_coverage_and_export_links_share_the_selected_campus_scope(app, client, mode, selected, expected):
    _login_as(client, _create_user(app, role='director'))
    args = [('period', 'all'), ('campus_mode', mode), ('goal_year', '2024'),
            ('award_year', '2026'), ('calendar_year', '2032'), ('calendar_month', '12')]
    args.extend(('campus', str(value)) for value in selected)
    contexts = []
    def capture(sender, template, context, **extra):
        contexts.append(context)
    with template_rendered.connected_to(capture, app):
        page = parse_html(client.get('/director_dash', query_string=args).get_data(as_text=True))
    context = contexts[-1]
    assert context['campus_coverage']['total'] == expected
    assert sum(row['activities'] for row in context['campus_coverage']['campuses']) == sum(
        row['campus_id'] is not None for row in context['evidence_rows'])
    values = form_values(page.one('form', id='analytics-filters'))
    assert values['goal_year'] == ['2024'] and values['calendar_month'] == ['12']
    links = [link for link in page.all('a') if '/reports/university.' in link.attrs.get('href', '')]
    assert len(links) == 2
    for link in links:
        scope = parse_qs(urlsplit(link.attrs['href']).query)
        assert scope['campus_mode'] == [mode] and scope['campus'] == [str(value) for value in selected]
    _, analytics, report = rendered(app, client,
        next(link.attrs['href'] for link in page.all('a') if link.text == 'View Activity Report'))
    assert context['performance'] == report['performance']


def test_invalid_dashboard_campus_scope_shows_error_without_broadening(app, client):
    _login_as(client, _create_user(app, role='director'))
    response, page, context = rendered(app, client, '/director_dash?campus=bad&period=all')
    assert response.status_code == 400
    assert page.one('p', **{'role': 'alert'})
    assert context['performance']['activities'] == 0
    assert context['campus_coverage']['total'] == 0


def test_attention_filter_groups_with_filters_not_actions(app, client):
    _login_as(client, _create_user(app, role='director'))
    _, page, _ = rendered(app, client, '/director_dash?period=all')
    panel = page.one('section', id='filters')
    primary = panel.one('div', **{'class': 'analytics-filter-primary'})
    assert primary.one('select', name='attention')
    actions = panel.one('div', **{'class': 'analytics-filter-actions'})
    assert not actions.all('select', name='attention')
    search = primary.one('input', name='activity_name')
    assert search.attrs['placeholder'] == 'Search activity titles'
    assert search.attrs['aria-describedby'] == 'activity-name-help'
    assert primary.one('small', id='activity-name-help')


def test_filters_report_scope_count_and_removable_chips(app, client):
    _login_as(client, _create_user(app, role='director'))
    _, page, _ = rendered(app, client, '/director_dash?period=all&category=Environment&activity_name=clean')
    panel = page.one('section', id='filters')
    count = panel.one('p', **{'class': 'filter-result-count'})
    assert count.text.endswith('in this scope')
    chips = panel.all('a', **{'class': 'filter-chip'})
    assert [chip.text.startswith(label) for chip, label in zip(chips, ['Activity: clean', 'Category: Environment'])]
    assert [chip.attrs['aria-label'] for chip in chips] == [
        'Remove filter: Activity: clean', 'Remove filter: Category: Environment']
    removing_activity, removing_category = (parse_qs(urlsplit(chip.attrs['href']).query) for chip in chips)
    assert removing_activity.get('category') == ['Environment'] and 'activity_name' not in removing_activity
    assert removing_category.get('activity_name') == ['clean'] and 'category' not in removing_category
    assert all(urlsplit(chip.attrs['href']).fragment == 'cross-campus-comparison' for chip in chips)


def test_filters_hide_clear_all_until_a_filter_applies(app, client):
    _login_as(client, _create_user(app, role='director'))
    _, plain, _ = rendered(app, client, '/director_dash?period=all')
    assert not [link for link in plain.one('section', id='filters').all('a') if link.text == 'Clear All Filters']
    _, filtered, _ = rendered(app, client, '/director_dash?period=all&category=Environment')
    clear = next(link for link in filtered.one('section', id='filters').all('a')
                 if link.text == 'Clear All Filters')
    assert parse_qs(urlsplit(clear.attrs['href']).query) == {}


def test_filters_zero_state_confirms_scope_and_recovery(app, client):
    _login_as(client, _create_user(app, role='director'))
    _, page, context = rendered(app, client, '/director_dash?period=all&activity_name=NoSuchActivity')
    assert context['evidence_rows'] == []
    zero = page.one('section', id='filters').one('p', **{'class': 'empty-state filter-zero-state'})
    assert 'No activities match this scope.' in zero.text
    assert 'Clear All Filters' in zero.text
    assert page.one('p', **{'class': 'filter-result-count'}).text == '0 activities in this scope'


def test_campus_picker_reads_as_one_of_the_advanced_filter_fields(app, client):
    _login_as(client, _create_user(app, role='director'))
    _, page, _ = rendered(app, client, '/director_dash?period=all')
    content = page.one('div', **{'class': 'analytics-advanced-filters__content'})
    picker = content.one('details', **{'class': 'campus-filter analytics-campus-filter'})
    assert picker.one('span', **{'class': 'campus-filter__label'}).text == 'Campus'
    assert picker.one('span', **{'class': 'campus-filter__value'}).text == 'All campuses'
    assert picker.one('select', name='campus_mode')
    _, excluded, _ = rendered(
        app, client, '/director_dash?period=all&campus=1&campus=2&campus_mode=exclude')
    value = excluded.one('span', **{'class': 'campus-filter__value'})
    assert value.text == '2 excluded'
