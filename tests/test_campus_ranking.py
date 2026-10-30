"""The director ranking shares campus goal definitions and uses exact ratios."""
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from app.annual_goals import campus_ranking, dashboard_context
from tests.test_annual_goals import app, client, target, _login_as, _create_user


def campus(name, met, total, campus_id=1, pending=0):
    return dict(campus=name, campus_id=campus_id, met=met, total=total, pending=pending,
                rate=round(met/total*100,1) if total else None)


def test_single_leader_counts_pending_and_excludes_no_targets():
    ranked = campus_ranking([campus('Pending campus',1,4,1,pending=3),
                             campus('Leader',2,3,2),campus('No targets',0,0,3)])
    assert ranked['state'] == 'ranked'
    assert [item['campus'] for item in ranked['leaders']] == ['Leader']
    assert len(ranked['rows']) == 2 and ranked['rows'][1]['pending'] == 3


def test_exact_ties_with_different_denominators_are_retained():
    ranked = campus_ranking([campus('Zulu',1,2,1),campus('Alpha',2,4,2),campus('Other',1,3,3)])
    assert [item['campus'] for item in ranked['leaders']] == ['Alpha','Zulu']


def test_rounding_does_not_create_false_ties():
    first, second = campus('Rounded lower',2,3,1), campus('Rounded higher',667,1000,2)
    assert first['rate'] == second['rate'] == 66.7
    assert campus_ranking([first,second])['leaders'] == [second]


@pytest.mark.parametrize('rows,state', [([], 'unavailable'),([campus('None',0,0)],'unavailable'),
    ([campus('Pending',0,4,pending=4),campus('Unmet',0,2,2)],'zero')])
def test_empty_and_zero_states_do_not_name_a_winner(rows,state):
    result = campus_ranking(rows)
    assert result['state'] == state and result['leaders'] == []


def test_director_routes_reuse_scoped_deduplicated_goals_without_sex_queries(app,client,monkeypatch):
    target(campus=1,actual=4,shared='campus-shared')
    target(campus=1,actual=4,shared='campus-shared',kind='ASP')
    target(campus=2,actual=4)
    target(campus=2)
    uid = _create_user(app,email='campus-ranking-director@test.com',role='director',campus_id=1)
    _login_as(client,uid)
    forbidden = Mock(side_effect=AssertionError('Director hero must not calculate sex participation'))
    monkeypatch.setattr('app.annual_goals.participation',forbidden)
    for path in ['/director_dash','/analytics']:
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert ('Worst Performing Campus' if path == '/director_dash' else 'Top-Performing Campus') in body
        assert 'goal-campus-ranking' in body
        assert ('50.0% · 1 of 2 Goals Achieved' if path == '/director_dash' else '100.0% · 1 of 1 Goals Achieved') in body
        assert 'Participation by Recorded Sex' not in body
    forbidden.assert_not_called()
    monkeypatch.undo()
    assert 'Actual participation by recorded sex' in client.get('/annual-goals?campus=1').get_data(as_text=True)


def test_sample_year_and_drilldowns_preserved(app,monkeypatch):
    comparisons = Mock(return_value=[campus('Sample campus',3,4,2)])
    monkeypatch.setattr('app.annual_goals.comparisons',comparisons)
    with app.test_request_context('/director_dash?goal_year=2024&sample=1'):
        plan = dashboard_context(2026)
    comparisons.assert_called_once_with(2024,True)
    assert plan['sample'] and plan['year'] == 2024
    assert parse_qs(urlsplit(plan['campus_ranking']['rows'][0]['detail_url']).query) == {
        'year':['2024'],'campus':['2'],'sample':['1']}


def test_coordinator_still_gets_participation_and_director_empty_preview_states(app,client):
    uid = _create_user(app,email='campus-ranking-coordinator@test.com',role='coordinator',campus_id=1)
    _login_as(client,uid)
    for path in ['/coordinator_dash','/coordinator_analytics']:
        body = client.get(path).get_data(as_text=True)
        assert 'Participation by Recorded Sex' in body and 'goal-campus-ranking' not in body
    uid = _create_user(app,email='campus-ranking-empty@test.com',role='director',campus_id=1)
    _login_as(client,uid)
    body = client.get('/director_dash').get_data(as_text=True)
    assert 'No approved campus targets for this year.' in body
    target(campus=1)
    body = client.get('/director_dash').get_data(as_text=True)
    assert 'Worst Performing Campus' in body and '0.0% · 0 of 1 Goals Achieved' in body
    preview = client.get('/director_dash?sample=1').get_data(as_text=True)
    assert '4 Campuses Tied' in preview and 'Lowest Annual Goal-Achievement Rate · Sample Data' in preview
    assert 'Worst Performing Campus' in client.get('/director_dash').get_data(as_text=True)
