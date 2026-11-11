from urllib.parse import parse_qs, urlsplit

from app.models import db
from app.models.event import Event, Registration, ExternalParticipant, CancellationRequest
from tests.test_app import app, client, _create_user, _login_as
from tests.html_helpers import parse_html


def test_cancellation_activity_filter_preserves_scope_and_review(app, client):
    uid = _create_user(app, role='coordinator', campus_id=1)
    _login_as(client, uid)
    with app.app_context():
        activities = Event.query.filter_by(campus_id=1).order_by(Event.id).all()
        selected, other, empty = [item.id for item in activities[:3]]
        outside = Event.query.filter_by(campus_id=2).first().id
        for index, event_id in enumerate([selected] * 26 + [other, outside]):
            person = ExternalParticipant(id_number=f'CANCEL-{index}', name=f'Cancel Person {index}')
            db.session.add(person)
            db.session.flush()
            registration = Registration(event_id=event_id, external_participant_id=person.id,
                                        status='confirmed')
            db.session.add(registration)
            db.session.flush()
            cancellation = CancellationRequest(registration_id=registration.id,
                                               reason='Academic Conflict')
            db.session.add(cancellation)
            db.session.flush()
            if index == 0:
                request_id = cancellation.id
        db.session.commit()
    path = f'/coordinator/cancellation-requests?event_id={selected}'
    response = client.get(path)
    assert response.status_code == 200
    page = parse_html(response.get_data(as_text=True))
    assert len(page.all('article')) == 25
    assert '26 requests' in page.text
    assert str(outside) not in [option.attrs.get('value') for option in
                               page.one('select', name='event_id').all('option')]
    next_link = page.one('nav', **{'aria-label': 'Cancellation request pages'}).one('a', rel='next')
    assert parse_qs(urlsplit(next_link.attrs['href']).query)['event_id'] == [str(selected)]
    for link in page.one('nav', **{'aria-label': 'Request status'}).all('a'):
        assert parse_qs(urlsplit(link.attrs['href']).query)['event_id'] == [str(selected)]
    page_two = parse_html(client.get(path + '&page=2').get_data(as_text=True))
    assert len(page_two.all('article')) == 1
    assert 'Cancel Person 26' not in page_two.text
    assert client.get(f'/coordinator/cancellation-requests?event_id={outside}').status_code == 403
    assert client.get('/coordinator/cancellation-requests?event_id=invalid').status_code == 403
    body = client.get(f'/coordinator/cancellation-requests?event_id={empty}').get_data(as_text=True)
    assert 'No pending cancellation requests for this activity' in body
    response = client.post(path, data={'request_id': request_id, 'decision': 'approved'})
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query)['event_id'] == [str(selected)]
    page = parse_html(client.get(path + '&status=approved').get_data(as_text=True))
    assert len(page.all('article')) == 1
    assert 'Cancel Person 0' in page.text
