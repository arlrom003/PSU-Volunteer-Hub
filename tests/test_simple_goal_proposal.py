from datetime import date

from app.models import db
from app.models.annual_plan import AnnualGoalProposal, AnnualTarget
from tests.test_app import app, client, _create_user
from tests.test_annual_goals import _login_as, definition
from tests.html_helpers import parse_html


def test_four_field_proposal_saves_submits_and_publishes(app, client):
    coordinator = _create_user(app, role='coordinator', campus_id=1)
    reviewer = _create_user(app, email='simple-director@test.com', role='director', campus_id=1)
    _login_as(client, coordinator)
    page = parse_html(client.get('/annual-goals/proposals/new').get_data(as_text=True))
    form = page.one('form', **{'class': 'goal-form'})
    fields = {element.attrs['name'] for tag in ('input', 'select', 'textarea')
              for element in form.all(tag) if element.attrs.get('type') != 'hidden'}
    assert fields == {'year', 'plan_type', 'responsible_office', 'target_value'}
    values = dict(year=date.today().year, plan_type='ASP', responsible_office='Extension Office',
                  target_value='4', action='save')
    response = client.post('/annual-goals/proposals/new', data=values)
    assert response.status_code == 302
    proposal = AnnualGoalProposal.query.one()
    assert proposal.status == 'draft' and proposal.campus_id == 1
    assert proposal.payload['evidence_basis'] == 'activities'
    assert proposal.payload['comparison_rule'] == 'gte'
    assert proposal.payload['unit'] == 'activities'
    path = f'/annual-goals/proposals/{proposal.id}/edit'
    invalid = dict(values, target_value='1.5')
    assert client.post(path, data=invalid).status_code == 400
    assert AnnualGoalProposal.query.one().payload['target_value'] == '4'
    values['action'] = 'submit'
    assert client.post(path, data=values).status_code == 302
    _login_as(client, reviewer)
    review = parse_html(client.get(f'/annual-goals/proposals/{proposal.id}').get_data(as_text=True))
    details = review.one('dl', **{'class': 'goal-definition'})
    assert [label.text for label in details.all('dt')] == ['Year', 'Plan', 'Responsible Office', 'Target']
    assert 'At least 4 activities' in details.text
    assert 'COMPLETED-ACTIVITIES' not in review.text
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action': 'approve'}).status_code == 302
    target = AnnualTarget.query.one()
    assert target.indicator.evidence_basis == 'activities'
    assert target.indicator.responsible_office == 'Extension Office'
    assert target.indicator.plan.plan_type == 'ASP'
    assert target.target_value == 4


def test_existing_proposal_retains_reporting_definition_on_simple_edit(app, client):
    coordinator = _create_user(app, role='coordinator', campus_id=1)
    _login_as(client, coordinator)
    original = definition()
    proposal = AnnualGoalProposal(campus_id=1, proposed_by_id=coordinator,
                                  payload=original, history=[])
    db.session.add(proposal)
    db.session.commit()
    response = client.post(f'/annual-goals/proposals/{proposal.id}/edit', data={
        'year': original['year'], 'plan_type': 'AOP', 'responsible_office': 'Updated Office',
        'target_value': '8', 'action': 'save'})
    assert response.status_code == 302
    payload = db.session.get(AnnualGoalProposal, proposal.id).payload
    for field in ('program', 'code', 'name', 'definition', 'unit', 'source_document',
                  'comparison_rule', 'evidence_basis', 'deadline'):
        assert payload[field] == original[field]
    assert payload['responsible_office'] == 'Updated Office'
    assert payload['target_value'] == '8'
