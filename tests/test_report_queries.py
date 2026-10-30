from datetime import datetime, timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event

from app.models import db
from app.models.event import Attendance, Event, ExternalParticipant, Registration
from app.models.user import User
from app.reports import build_events_report
from tests.test_app import app


@pytest.mark.parametrize('event_count', [1, 200])
def test_report_query_count_does_not_grow_with_registrations(app, event_count):
    now = datetime(2026, 10, 30, 12)
    people = [ExternalParticipant(id_number=f'query-person-{i}') for i in range(25)]
    db.session.add_all(people)
    db.session.flush()
    cases = [('completed', 'present'), ('confirmed', 'present'),
             ('confirmed', None), ('confirmed', 'absent'), ('cancelled', 'present')]
    for i in range(event_count):
        activity = Event(title=f'Query budget {i}', description='Query regression',
                         date=now - timedelta(days=1), campus_id=1)
        db.session.add(activity)
        db.session.flush()
        for j, person in enumerate(people):
            status, attendance = cases[j % len(cases)]
            registration = Registration(event_id=activity.id,
                external_participant_id=person.id, status=status)
            db.session.add(registration)
            db.session.flush()
            if attendance:
                db.session.add(Attendance(registration_id=registration.id,
                    event_id=activity.id, status=attendance))
    db.session.commit()
    db.session.remove()

    queries = []
    def record(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    sqlalchemy_event.listen(db.engine, 'before_cursor_execute', record)
    try:
        rows, summary = build_events_report(activity_name='Query budget', now=now)
    finally:
        sqlalchemy_event.remove(db.engine, 'before_cursor_execute', record)

    assert len(rows) == event_count
    assert summary['total_registrations'] == event_count * 20
    assert summary['total_external'] == event_count * 20
    assert summary['total_attended'] == event_count * 15
    assert summary['total_completed'] == event_count * 5
    assert summary['total_cancelled'] == event_count * 5
    for row in rows:
        assert row['missing_attendance'] == 5
        assert row['unconfirmed_present'] == 5
        assert row['outcome_attended'] == 10
        assert not row['attendance_complete']
    assert len(queries) <= 4, f'Report issued {len(queries)} queries'


@pytest.mark.parametrize('sex,registrations,attended,completed,outcome', [
    (None, 5, 4, 2, 3), ('female', 2, 1, 1, 2), ('male', 1, 1, 0, 1),
    ('prefer_not_to_say', 1, 0, 0, 0), ('unrecorded', 0, 1, 0, 0),
])
def test_batched_counts_preserve_filtered_and_whole_event_evidence(
        app, sex, registrations, attended, completed, outcome):
    now = datetime(2026, 10, 30, 12)
    activity = Event(title='Filtered counts', description='Filter regression',
                     date=now - timedelta(days=1), campus_id=1)
    users = [User(name=f'Filter {i}', email=f'filter-{i}@example.test',
                  sex=value, password_hash='unused')
             for i, value in enumerate(['female', 'male', 'prefer_not_to_say', None, 'female'])]
    external = ExternalParticipant(id_number='filtered-external', sex='female')
    db.session.add_all([activity, external, *users])
    db.session.flush()
    cases = [(users[0], 'completed', 'present'), (users[1], 'confirmed', 'present'),
             (users[2], 'confirmed', 'absent'), (users[3], 'cancelled', 'present'),
             (external, 'completed', None)]
    for person, status, attendance in cases:
        registration = Registration(event_id=activity.id, status=status,
            **({'external_participant_id': person.id} if person is external else {'user_id': person.id}))
        db.session.add(registration)
        db.session.flush()
        if attendance:
            db.session.add(Attendance(registration_id=registration.id, event_id=activity.id,
                user_id=None if person is external else person.id, status=attendance))
    registration = Registration(event_id=activity.id, user_id=users[4].id, status='confirmed')
    db.session.add(registration)
    db.session.flush()
    db.session.add(Attendance(registration_id=registration.id, event_id=activity.id, status='present'))
    db.session.commit()

    rows, _ = build_events_report(activity_name='Filtered counts', sex=sex, now=now)
    row = rows[0]
    assert row['registrations'] == registrations
    assert row['attended'] == attended
    assert row['completed'] == completed
    assert row['outcome_attended'] == outcome
    assert row['cancelled'] == 1
    assert row['missing_attendance'] == 1
    assert row['unconfirmed_present'] == 2
    assert not row['attendance_complete']
