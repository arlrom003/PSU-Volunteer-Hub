"""Decision findings must distinguish unfinished records from verified outcomes."""
from datetime import datetime, timedelta
from html import unescape
import re

import pytest
from flask import template_rendered

from tests.test_app import app, client, _create_user, _login_as
from app.models import db
from app.models.event import Event, Registration, Attendance, ExternalParticipant, CancellationRequest
from app.dashboard import resolve_period, performance_summary, consolidate_attention
from app.reports import build_events_report, ReportError


@pytest.mark.parametrize('today,expected', [
    (datetime(2026, 3, 31), ('2026-02-01', '2026-02-28')),
    (datetime(2024, 3, 31), ('2024-02-01', '2024-02-29')),
    (datetime(2026, 1, 1), ('2025-12-01', '2025-12-01')),
])
def test_comparison_matches_elapsed_days(today, expected):
    period = resolve_period({}, today)
    assert period['start'] == today.replace(day=1).date().isoformat()
    assert period['end'] == today.date().isoformat()
    assert period['comparison'] == expected


def test_explicit_and_all_date_periods_do_not_claim_comparisons():
    assert resolve_period({'period': 'all'})['comparison'] is None
    custom = resolve_period({'start_date': '2026-01-01', 'end_date': '2026-01-31'})
    assert custom['value'] == 'custom' and custom['comparison'] is None
    assert resolve_period({'start_date': '', 'end_date': ''})['value'] == 'all'
    with pytest.raises(ReportError):
        resolve_period({'start_date': '2026-02-01', 'end_date': '2026-01-01'})
    with pytest.raises(ReportError):
        resolve_period({'period': 'unknown'})


@pytest.fixture
def decisions(app):
    now = datetime.now()
    cases = [
        ('Recorded low attendance', -3, ['present', 'absent', 'absent', 'excused'], True, 3, 1),
        ('Exactly seventy five', -2, ['present', 'present', 'present', 'absent'], True, 3, 1),
        ('Missing attendance', -4, [None, 'present'], True, 2, 1),
        ('Completion confirmation', -1, ['present'], False, 1, 1),
        ('Upcoming target', 2, [None], False, 20, 1),
        ('Other campus outcome', -2, ['absent'], True, 5, 2),
        ('No registrations or target', -2, [], True, None, 1),
    ]
    records = {}
    for index, (title, days, statuses, confirmed, target, campus) in enumerate(cases):
        event = Event(title=title, description='Decision evidence',
                      date=now + timedelta(days=days), campus_id=campus,
                      target_participants=target, slots=20)
        db.session.add(event)
        db.session.flush()
        records[title] = event.id
        for number, attendance in enumerate(statuses):
            participant = ExternalParticipant(id_number=f'decision-{index}-{number}', name='Example participant')
            db.session.add(participant)
            db.session.flush()
            registration = Registration(event_id=event.id, external_participant_id=participant.id,
                status='completed' if attendance == 'present' and confirmed else 'confirmed')
            db.session.add(registration)
            db.session.flush()
            if attendance:
                db.session.add(Attendance(registration_id=registration.id, event_id=event.id, status=attendance))
    db.session.commit()
    return records


def test_outcomes_exclude_unfinished_and_future_activities(app, decisions):
    rows, _ = build_events_report(campus_id=1, activity_name='')
    rows = [row for row in rows if row['event_id'] in decisions.values()]
    summary = performance_summary(rows)
    assert {row['title'] for row in summary['pending']} == {'Missing attendance', 'Completion confirmation'}
    assert {row['title'] for row in summary['low']} == {'Recorded low attendance'}
    assert {row['title'] for row in summary['missed']} == {'Recorded low attendance'}
    assert summary['rate'] == 50.0
    assert summary['targets_met'] == 1 and summary['targets_count'] == 2
    assert summary['rate_registrations'] == 8
    assert performance_summary([], False)['rate'] is None
    assert performance_summary(rows, False)['targets_count'] == 0
    assert performance_summary(rows, False)['missed'] == []


def test_missing_records_and_completion_confirmation_are_separate(app, decisions):
    rows, _ = build_events_report(attention='pending_attendance', campus_id=1)
    by_title = {row['title']: row for row in rows}
    assert by_title['Missing attendance']['missing_attendance'] == 1
    assert by_title['Missing attendance']['unconfirmed_present'] == 0
    assert by_title['Completion confirmation']['missing_attendance'] == 0
    assert by_title['Completion confirmation']['unconfirmed_present'] == 1
    assert 'Upcoming target' not in by_title


def test_attention_filters_keep_report_totals_and_scope(app, decisions):
    for attention in ['low_attendance', 'missed_targets']:
        rows, summary = build_events_report(campus_id=1, attention=attention)
        assert [row['title'] for row in rows] == ['Recorded low attendance']
        assert summary['event_count'] == 1
        assert summary['total_registrations'] == 4
        assert summary['total_attended'] == 1
    with pytest.raises(ReportError):
        build_events_report(attention='not-valid')
    with pytest.raises(ReportError):
        build_events_report(attention='missed_targets', sex='female')
    with pytest.raises(ReportError):
        build_events_report(event_id='invalid')
    assert build_events_report(campus_id=1, event_id=decisions['Other campus outcome'])[0] == []


def test_cancelled_registration_does_not_leave_attendance_pending(app, decisions):
    event_id = decisions['Missing attendance']
    Registration.query.filter_by(event_id=event_id).filter(
        ~Registration.attendance_record.has()).one().status = 'cancelled'
    db.session.commit()
    row = build_events_report(event_id=event_id)[0][0]
    assert row['attendance_complete']
    assert row['registrations'] == 1


def test_ongoing_and_unfinished_target_results_are_not_judged(app, decisions):
    event = db.session.get(Event, decisions['Recorded low attendance'])
    event.end_date = datetime.now() + timedelta(days=1)
    db.session.commit()
    row = build_events_report(event_id=event.id)[0][0]
    assert not row['ended'] and not row['attendance_complete']
    assert row['completion_percentage'] is None
    summary = performance_summary([row])
    assert summary['rate'] is None and not summary['pending']
    assert not summary['low'] and not summary['missed']
    assert build_events_report(event_id=decisions['Missing attendance'])[0][0]['completion_percentage'] is None
    subset = build_events_report(event_id=decisions['Exactly seventy five'], sex='female')[0][0]
    assert subset['completion_percentage'] is None


def test_weighted_rate_uses_registrations_not_average_percentages():
    rows = [dict(attendance_complete=True, ended=True, registrations=1, attended=1,
                 outcome_attended=1, target_participants=None),
            dict(attendance_complete=True, ended=True, registrations=9, attended=1,
                 outcome_attended=1, target_participants=0)]
    summary = performance_summary(rows)
    assert summary['rate'] == 20.0
    assert summary['targets_count'] == 0


def test_attention_merges_reasons_without_repeating_activity(app, decisions):
    rows, _ = build_events_report(campus_id=1)
    summary = performance_summary(rows)
    items = consolidate_attention(summary)
    low = [item for item in items if item['event_id'] == decisions['Recorded low attendance']]
    assert len(low) == 1 and len(low[0]['reasons']) == 2
    assert 'target' in low[0]['reasons'][0]
    assert '75%' in low[0]['reasons'][1]
    assert len({item['event_id'] for item in items}) == len(items)
    assert items[0]['is_pending']


@pytest.mark.parametrize('role,path,export', [
    ('director', '/analytics', '/reports/university.csv'),
    ('coordinator', '/coordinator_analytics', '/reports/events.csv'),
])
def test_drilldowns_exports_and_html_agree(app, client, decisions, role, path, export, monkeypatch):
    uid = _create_user(app, email=f'{role}-decisions@test.com', role=role, campus_id=1)
    _login_as(client, uid)
    query = '?start_date=&end_date=&attention=low_attendance&campus=1&campus_mode=include'
    contexts = []
    def capture(sender, template, context, **extra):
        contexts.append(context)
    with template_rendered.connected_to(capture, app):
        response = client.get(path + query)
    assert response.status_code == 200
    assert contexts[-1]['performance']['activities'] == 1
    assert contexts[-1]['performance']['rate'] == 25.0
    csv = client.get(export + query).get_data(as_text=True)
    assert 'Recorded low attendance' in csv
    assert 'Other campus outcome' not in csv
    assert 'Missing attendance' not in csv
    def pdf(rows, summary, meta):
        assert [row['title'] for row in rows] == ['Recorded low attendance']
        assert summary['event_count'] == 1
        assert '75%' in meta['scope']
        return b'%PDF-decision-evidence'
    monkeypatch.setattr(f'app.routes.{role}.render_pdf', pdf)
    assert client.get(export.replace('.csv', '.pdf') + query).data == b'%PDF-decision-evidence'
    body = response.get_data(as_text=True)
    export_links = re.findall(r'href="([^"]+\.csv[^\"]*)"', body)
    assert export_links and 'attention=low_attendance' in unescape(export_links[0])


@pytest.mark.parametrize('role,path', [('director', '/director_dash'), ('coordinator', '/coordinator_dash')])
def test_landing_pages_explain_scope_and_next_action(app, client, decisions, role, path):
    if role == 'coordinator':
        registration = Registration.query.filter_by(event_id=decisions['Upcoming target']).one()
        db.session.add(CancellationRequest(registration_id=registration.id, reason='Schedule conflict'))
        db.session.commit()
    uid = _create_user(app, email=f'{role}-overview@test.com', role=role, campus_id=1)
    _login_as(client, uid)
    response = client.get(path)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Performance Period' in body
    assert 'Performance Overview' in body
    if role == 'coordinator':
        assert 'Attendance work across all dates' in body
        assert 'Missing attendance' in body
        assert 'awaiting completion confirmation' in body
        assert body.index('Needs Attention') < body.index('Performance Overview')
    else:
        assert 'Needs Attention' not in body
        assert 'Campus Activity Coverage' in body
    event_ids = re.findall(r'data-attention-event="(\d+)"', body)
    assert len(event_ids) == len(set(event_ids))
    assert 'How these numbers are counted' not in body
    if role == 'coordinator':
        assert re.search(r'<section[^>]+id="activity-workspace"', body)
        assert not re.search(r'<details[^>]+id="activity-workspace"', body)
        filtered = client.get(path + '?workspace=1&status=all').get_data(as_text=True)
        assert re.search(r'<section[^>]+id="activity-workspace"', filtered)
    if role == 'coordinator':
        assert '1 Request Awaits' in body and 'Review Requests' in body
