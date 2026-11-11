from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from app.models import db
from app.models.event import Attendance, Event, ExternalParticipant, Registration
from tests.test_app import app, client, _create_user, _login_as


def test_attendance_search_filters_pages_and_save(app, client):
    coordinator = _create_user(app, email='roster-coordinator@test.com',
                               role='coordinator', campus_id=1)
    volunteer = _create_user(app, email='roster-student@test.com',
                             name='Campus Needle', campus_id=1)
    _login_as(client, coordinator)
    with app.app_context():
        activity = Event.query.filter_by(title='Youth Coding Mentor').one()
        activity.date = datetime.now() - timedelta(days=1)
        event_id = activity.id
        for index in range(16):
            person = ExternalParticipant(id_number=f'ROSTER-{index:02}',
                                         name=f'Roster Person {index:02}',
                                         email=f'roster-{index}@example.com')
            db.session.add(person)
            db.session.flush()
            registration = Registration(event_id=event_id,
                external_participant_id=person.id, status='confirmed')
            db.session.add(registration)
            db.session.flush()
            if index == 15:
                target_id = registration.id
                db.session.add(Attendance(registration_id=registration.id,
                    event_id=event_id, status='absent'))
        db.session.add(Registration(event_id=event_id, user_id=volunteer, status='confirmed'))
        db.session.commit()

    path = f'/attendance?event_id={event_id}'
    body = client.get(path).get_data(as_text=True)
    assert body.count('name="registration_id"') == 15
    assert 'Page 1 of 2' in body
    body = client.get(path + '&volunteer_search=Roster&page=2').get_data(as_text=True)
    assert body.count('name="registration_id"') == 2
    assert 'volunteer_search=Roster' in body
    for query in ('Person 15', 'roster-15@example.com', 'ROSTER-15'):
        body = client.get('/attendance', query_string={
            'event_id': event_id, 'volunteer_search': query,
            'attendance_status': 'absent'}).get_data(as_text=True)
        assert body.count('name="registration_id"') == 1
        assert 'Roster Person 15' in body
    body = client.get(path + '&volunteer_search=Campus%20Needle').get_data(as_text=True)
    assert body.count('name="registration_id"') == 1
    body = client.get(path + '&attendance_status=unmarked').get_data(as_text=True)
    assert '16 matching volunteers' in body
    assert 'Roster Person 15' not in body
    body = client.get(path + '&volunteer_search=%25').get_data(as_text=True)
    assert 'No volunteers match' in body
    assert 'Clear Filters' in body

    response = client.post(path + '&volunteer_search=ROSTER-15&attendance_status=absent',
        data={'event_id': event_id, 'registration_id': target_id, 'status': 'present'})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.location).query)
    assert query['volunteer_search'] == ['ROSTER-15']
    assert query['attendance_status'] == ['absent']
    with app.app_context():
        assert db.session.get(Registration, target_id).attendance_record.status == 'present'
        assert Attendance.query.filter_by(event_id=event_id).count() == 1
