"""Goal workflows and evidence must respect approval, scope, and counting rules."""
import csv
import io
from datetime import date, datetime, timedelta

import pytest

from tests.test_app import app, client, _create_user, _login_as as base_login
from flask import g
from app.models import db
from app.models.annual_plan import (AnnualPlan, AnnualIndicator, AnnualTarget, AnnualResult,
                                   AnnualGoalProposal, AnnualActivityMapping)
from app.models.event import Event, ExternalParticipant, Registration, Attendance
from app.annual_goals import summary, participation
from app.annual_import import import_file
from app.reports import ReportError


def _login_as(client, uid):
    # The shared fixture holds an app context across requests, unlike production.
    g.pop('_login_user', None)
    base_login(client, uid)


def definition(**changes):
    return dict(year=str(date.today().year), plan_type='AOP', program='Community learning', code='AOP-1',
                name='Learning programs delivered', definition='Count fully delivered community programs.',
                unit='programs', responsible_office='Extension Office', source_document='Approved plan reference',
                target_value='4', comparison_rule='gte', evidence_basis='approved_aggregate', deadline='', **changes)


def target(campus=None, kind='AOP', shared=None, actual=None, value=4, rule='gte', basis='approved_aggregate'):
    key = str(AnnualTarget.query.count())
    plan = AnnualPlan(source_key='plan-'+key, year=date.today().year, plan_type=kind,
                      title='Approved fixture', source_document='Test approval')
    db.session.add(plan); db.session.flush()
    indicator = AnnualIndicator(source_key='indicator-'+key, plan_id=plan.id, code='GOAL-'+key,
        name='Delivered programs', program='Community learning', unit='programs', definition='Count programs',
        responsible_office='Extension Office', shared_key=shared, evidence_basis=basis)
    db.session.add(indicator); db.session.flush()
    item = AnnualTarget(source_key='target-'+key, indicator_id=indicator.id, campus_id=campus,
                        target_value=value, comparison_rule=rule)
    db.session.add(item); db.session.flush()
    if actual is not None:
        db.session.add(AnnualResult(source_key='result-'+key, target_id=item.id, actual_value=actual,
            evidence_status='verified', result_type='approved_aggregate', source_document='Approved report',
            coverage_start=date(date.today().year, 1, 1), coverage_end=date.today(), coverage_note='Annual cumulative count'))
    db.session.commit()
    return item


def test_scope_shared_membership_zero_and_comparison_rules(app):
    target(actual=4, shared='same')
    target(actual=4, kind='ASP', shared='same')
    target(campus=1, actual=0, value=0, rule='eq')
    target(campus=1, actual=3, value=4, rule='lte')
    target(campus=1)
    target(campus=2, actual=0)
    university = summary()
    assert university['total'] == university['met'] == 1
    assert university['plans'] == {'AOP': {'total': 1, 'met': 1}, 'ASP': {'total': 1, 'met': 1}}
    campus = summary(campus_id=1)
    assert (campus['total'], campus['met'], campus['pending'], campus['remaining']) == (3, 2, 1, 0)
    assert campus['rate'] == 66.7
    assert summary(campus_id=3)['rate'] is None


def test_proposal_review_revision_and_cross_campus_permissions(app, client):
    coordinator = _create_user(app, email='goals-campus@test.com', role='coordinator', campus_id=1)
    reviewer = _create_user(app, email='goals-director@test.com', role='director', campus_id=1)
    outsider = _create_user(app, email='goals-other@test.com', role='coordinator', campus_id=2)
    _login_as(client, coordinator)
    response = client.post('/annual-goals/proposals/new', data=dict(definition(), action='submit', campus_id='2'))
    assert response.status_code == 302
    proposal = AnnualGoalProposal.query.one()
    assert proposal.campus_id == 1 and proposal.status == 'submitted'
    assert summary(campus_id=1)['total'] == 0
    _login_as(client, outsider)
    assert client.get(f'/annual-goals/proposals/{proposal.id}').status_code == 403
    assert client.post(f'/annual-goals/proposals/{proposal.id}/edit', data=definition()).status_code == 403
    _login_as(client, coordinator)
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action': 'approve'}).status_code == 403
    _login_as(client, reviewer)
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action':'return'}).status_code == 400
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action':'return', 'note':'Clarify the program definition.'}).status_code == 302
    _login_as(client, coordinator)
    assert client.post(f'/annual-goals/proposals/{proposal.id}/edit', data=dict(definition(), action='submit')).status_code == 302
    _login_as(client, reviewer)
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action':'approve'}).status_code == 302
    assert client.post(f'/annual-goals/proposals/{proposal.id}', data={'action':'approve'}).status_code == 409
    old = db.session.get(AnnualTarget, proposal.published_target_id)
    _login_as(client, coordinator)
    values = definition(); values['target_value'] = '8'
    assert client.post(f'/annual-goals/proposals/new?revise={old.id}', data=dict(values, action='submit')).status_code == 302
    assert old.is_active and summary(campus_id=1)['total'] == 1
    revision = AnnualGoalProposal.query.order_by(AnnualGoalProposal.id.desc()).first()
    _login_as(client, reviewer)
    assert client.post(f'/annual-goals/proposals/{revision.id}', data={'action':'approve'}).status_code == 302
    assert not old.is_active and summary(campus_id=1)['total'] == 1
    assert len(proposal.history) >= 4


def test_university_publish_cannot_be_done_by_coordinator(app, client):
    uid = _create_user(app, email='goal-university@test.com', role='coordinator', campus_id=1)
    _login_as(client, uid)
    assert client.post('/annual-goals/proposals/new', data=dict(definition(), action='publish')).status_code == 400
    assert AnnualTarget.query.count() == 0
    reviewer = _create_user(app, email='goal-publish@test.com', role='director', campus_id=1)
    _login_as(client, reviewer)
    assert client.post('/annual-goals/proposals/new', data=dict(definition(), action='publish')).status_code == 302
    assert summary()['total'] == 1 and summary(campus_id=1)['total'] == 0


def test_attendance_basis_cancellations_repeats_unknown_and_tie(app):
    today = datetime.now() - timedelta(days=1)
    if today.year != date.today().year:
        today = datetime.now()
    person = ExternalParticipant(id_number='goal-sex', sex='female')
    other = ExternalParticipant(id_number='goal-male', sex='male')
    unknown = ExternalParticipant(id_number='goal-unknown')
    db.session.add_all([person, other, unknown]); db.session.flush()
    for index, participant in enumerate([person, person, other, other, unknown, person]):
        event = Event(title=f'Annual evidence {index}', description='Fixture', campus_id=1, date=today)
        db.session.add(event); db.session.flush()
        reg = Registration(event_id=event.id, external_participant_id=participant.id,
            status='cancelled' if index == 5 else 'completed' if index < 4 else 'confirmed')
        db.session.add(reg); db.session.flush()
        db.session.add(Attendance(registration_id=reg.id, event_id=event.id, status='present'))
    db.session.commit()
    result = participation(date.today().year, 1)
    assert result['total'] == 5 and result['tie'] and result['share'] == 40
    assert result['missing'] == 1
    assert participation(date.today().year, 1, 'unique_attendees')['total'] == 3
    assert participation(date.today().year, 1, 'completed')['total'] == 4


def test_calculated_target_requires_complete_ended_records(app):
    item = target(campus=1, basis='verified_attendance', value=1)
    event = Event(title='Linked program', description='Fixture', campus_id=1,
                  date=datetime.now() - timedelta(hours=1))
    person = ExternalParticipant(id_number='goal-calculated')
    db.session.add_all([event,person]); db.session.flush()
    reg = Registration(event_id=event.id, external_participant_id=person.id, status='confirmed')
    db.session.add(reg); db.session.add(AnnualActivityMapping(target_id=item.id,event_id=event.id)); db.session.commit()
    assert summary(campus_id=1)['pending'] == 1
    db.session.add(Attendance(registration_id=reg.id,event_id=event.id,status='present'))
    db.session.commit()
    assert summary(campus_id=1)['pending'] == 1
    reg.status = 'completed'; db.session.commit()
    assert summary(campus_id=1)['met'] == 1


def test_sample_drilldown_export_isolation_and_all_templates(app, client):
    uid = _create_user(app, email='goals-preview@test.com', role='director', campus_id=1)
    _login_as(client, uid)
    before = AnnualTarget.query.count()
    for path in ['/director_dash?sample=1','/analytics?sample=1','/annual-goals?sample=1',
                 '/annual-goals?sample=1&campus=1&plan=AOP','/annual-goals/workspace','/annual-goals/proposals/new']:
        result = client.get(path)
        assert result.status_code == 200, (path,result.data[:200])
    assert client.get('/annual-goals?sample=1&export=csv').status_code == 400
    assert client.post('/annual-goals/proposals/new?sample=1', data=dict(definition(),action='publish')).status_code == 400
    assert AnnualTarget.query.count() == before
    official = client.get('/annual-goals?export=csv')
    assert b'SAMPLE-' not in official.data
    uid = _create_user(app, email='goals-preview-campus@test.com', role='coordinator', campus_id=1)
    _login_as(client, uid)
    for path in ['/coordinator_dash?sample=1','/coordinator_analytics?sample=1','/annual-goals?sample=1&campus=2']:
        assert client.get(path).status_code == 200
    assert b'Campus goal results' not in client.get('/annual-goals?sample=1').data


def test_filters_exports_and_evidence_route(app, client):
    item = target(actual=4)
    pending = target()
    uid = _create_user(app, email='goals-export@test.com', role='director', campus_id=1)
    _login_as(client, uid)
    for kind in ['csv','pdf']:
        response = client.get(f'/annual-goals?status=met&export={kind}')
        assert response.status_code == 200
        assert response.data.startswith(b'%PDF') if kind == 'pdf' else b'GOAL-0' in response.data and b'GOAL-1' not in response.data
    assert client.get(f'/annual-goals/targets/{item.id}/evidence').status_code == 200
    assert client.post(f'/annual-goals/targets/{item.id}/evidence', data={}).status_code == 400
    year = date.today().year
    response = client.post(f'/annual-goals/targets/{pending.id}/evidence', data=dict(actual_value='8',
        coverage_start=f'{year}-01-01', coverage_end=date.today().isoformat(), source_document='Approval 2',
        coverage_note='Cumulative annual count', approved='1'))
    assert response.status_code == 302 and summary()['met'] == 2
    assert client.get('/annual-goals?year=oops').status_code == 400
    assert client.get('/annual-goals?campus=999').status_code == 400


def test_import_dry_run_rollback_idempotence_and_conflicts(app, tmp_path):
    values = dict(plan_key='approved-aop', year=str(date.today().year), plan_type='AOP',plan_title='Annual operational plan',
        source_document='Approved AOP',indicator_key='approved-indicator', indicator_code='AOP-1',
        indicator_name='Programs',program='Community learning',unit='programs',responsible_office='Extension Office',
        target_key='approved-target', campus_code='LINGAYEN',target_value='4', approval_reference='Board reference',
        approval_date=date.today().isoformat(),evidence_basis='approved_aggregate')
    path = tmp_path / 'goals.csv'
    def write(records):
        with path.open('w',newline='',encoding='utf8') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(values)); writer.writeheader(); writer.writerows(records)
    write([values]); import_file(path,True)
    assert AnnualTarget.query.count() == 0
    import_file(path); import_file(path)
    assert AnnualTarget.query.count() == 1
    broken = dict(values, target_key='bad-target',indicator_key='bad-indicator',target_value='NaN')
    write([dict(values, target_key='new-target',indicator_key='new-indicator'),broken])
    with pytest.raises(ReportError, match='CSV line 3'):
        import_file(path)
    assert AnnualTarget.query.count() == 1
    write([dict(values, target_value='7')])
    with pytest.raises(ReportError, match='immutable'):
        import_file(path)


def test_shared_revision_keeps_memberships_and_old_evidence_history(app, client):
    old = target(campus=1, actual=4, shared='shared-goal')
    peer = target(campus=1, actual=4, kind='ASP', shared='shared-goal')
    uid = _create_user(app, email='shared-coordinator@test.com', role='coordinator', campus_id=1)
    reviewer = _create_user(app, email='shared-director@test.com', role='director', campus_id=1)
    _login_as(client, uid)
    assert client.post(f'/annual-goals/proposals/new?revise={old.id}', data=dict(definition(),action='submit')).status_code == 302
    proposal = AnnualGoalProposal.query.one()
    _login_as(client, reviewer)
    assert client.post(f'/annual-goals/proposals/{proposal.id}',data={'action':'approve'}).status_code == 302
    result = summary(campus_id=1)
    assert result['total'] == 1 and result['pending'] == 1
    assert result['plans']['AOP']['total'] == result['plans']['ASP']['total'] == 1
    assert not old.is_active and not peer.is_active
    assert AnnualResult.query.count() == 2


def test_invalid_targets_and_sample_posts_never_publish(app, client):
    uid = _create_user(app,email='bad-goal@test.com',role='director',campus_id=1)
    _login_as(client,uid)
    for invalid in ['NaN','Infinity','-1','1.00001']:
        data = definition(); data['target_value'] = invalid
        assert client.post('/annual-goals/proposals/new',data=dict(data,action='publish')).status_code == 400
    assert AnnualTarget.query.count() == AnnualGoalProposal.query.count() == 0
    assert client.get('/director_dash?goal_year=bogus').status_code == 400
    assert client.get('/annual-goals?sample=1&export=pdf').status_code == 400


def test_pagination_and_filters_do_not_change_whole_scope_judgment(app, client):
    for index in range(11):
        target(actual=4 if index % 2 else None)
    uid = _create_user(app,email='goal-pagination@test.com',role='director',campus_id=1)
    _login_as(client,uid)
    page = client.get('/annual-goals?page=2&plan=AOP')
    assert page.status_code == 200 and b'Page 2 of 2' in page.data
    assert b'GOAL-9' in page.data
    assert b'5 of 11 goals achieved' in client.get('/annual-goals?status=met').data
    assert b'GOAL-0' not in client.get('/annual-goals?status=met&export=csv').data
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/annual-goals/proposals/new',data=dict(definition(),action='publish')).status_code == 400
