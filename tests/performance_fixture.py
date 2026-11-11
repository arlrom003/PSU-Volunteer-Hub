"""Disposable benchmark records; this generator cannot target Railway."""
from datetime import datetime, timedelta, date
from pathlib import Path
from sqlalchemy import insert

from app.models import db
from app.models.user import User, VolunteerProfile
from app.models.event import (Event, Registration, Attendance, Campus, CancellationRequest,
                              HistoricalActivity, event_sdgs, event_skills)
from app.models.notification import Notification
from app.models.policy import TermsRevision, TermsAcceptance, PrivacyRevision, PrivacyAcknowledgement
from app.models.annual_plan import AnnualPlan, AnnualIndicator, AnnualTarget, AnnualActivityMapping


def build_performance_fixture(app, activity_count=1000):
    url = db.engine.url
    local = url.host in (None, '', 'localhost', '127.0.0.1')
    disposable = url.database == ':memory:' or Path(url.database or '').name.startswith('psu_perf_')
    if not app.testing or not local or not disposable or url.host and not (url.database or '').startswith('psu_perf_'):
        raise ValueError('Benchmark fixtures require an explicitly disposable local testing database.')
    if (Registration.query.count() or AnnualTarget.query.count() or Event.query.count() > 9
            or User.query.count() > 6 or TermsRevision.query.count() or PrivacyRevision.query.count()):
        raise ValueError('Create a fresh benchmark database; this generator never replaces existing participation.')
    db.session.execute(event_sdgs.delete())
    db.session.execute(event_skills.delete())
    db.session.execute(Event.__table__.delete())
    campuses = Campus.query.order_by(Campus.id).all()
    now = datetime.now()
    users = [dict(name=f'Benchmark Volunteer {i}', email=f'benchmark-{i}@example.test',
                  password_hash='unusable-benchmark-password', role='volunteer', campus_id=campuses[i % 9].id,
                  sex=('female', 'male', 'prefer_not_to_say')[i % 3]) for i in range(1000)]
    db.session.execute(insert(User), users)
    db.session.flush()
    people = User.query.filter(User.email.like('benchmark-%@example.test')).order_by(User.id).all()
    terms = TermsRevision(title='Volunteer terms', body='Policies for the local performance fixture.', version='performance-2026')
    privacy = PrivacyRevision(title='Volunteer privacy notice', body='Notice for the local performance fixture.', version='performance-2026')
    db.session.add_all([terms, privacy])
    db.session.flush()
    identities = [row[0] for row in db.session.query(User.id)]
    db.session.execute(insert(TermsAcceptance), [dict(user_id=identity, revision_id=terms.id) for identity in identities])
    db.session.execute(insert(PrivacyAcknowledgement), [dict(user_id=identity, revision_id=privacy.id) for identity in identities])
    db.session.execute(insert(VolunteerProfile), [dict(user_id=person.id) for person in people])
    activities = []
    for i in range(activity_count):
        start = now - timedelta(days=90) + timedelta(hours=i % 120) if i % 5 else now + timedelta(days=3 + i % 30)
        activities.append(dict(id=10000+i, title=f'Benchmark Activity {i}', description='Disposable performance fixture',
            date=start, end_date=start+timedelta(hours=3), cancellation_deadline=start-timedelta(days=1),
            campus_id=campuses[i % 9].id, category=('Environment', 'Education & Literacy')[i % 2],
            slots=60, target_participants=40))
    db.session.execute(insert(Event), activities)
    registrations, attendance, cancellations = [], [], []
    for i, activity in enumerate(activities):
        ended = activity['end_date'] < now
        for seat in range(50):
            identity = 10000 + i * 50 + seat
            person = people[(i * 31 + seat) % len(people)]
            cancelled = not ended and seat % 17 == 0
            present = ended and seat % 5 != 0
            status = 'cancelled' if cancelled else 'completed' if present else 'confirmed'
            registrations.append(dict(id=identity, event_id=activity['id'], user_id=person.id,
                                      status=status, registered_at=activity['date']-timedelta(days=5)))
            if ended and (i % 11 or seat < 25):
                attendance.append(dict(registration_id=identity, event_id=activity['id'], user_id=person.id,
                    status='present' if present else 'absent' if seat % 2 else 'excused'))
            if not ended and seat < 3:
                state = ('pending', 'approved', 'rejected')[seat]
                if state == 'approved':
                    registrations[-1]['status'] = 'cancelled'
                cancellations.append(dict(registration_id=identity, status=state, reason='Academic Conflict',
                    requested_at=activity['date']-timedelta(days=3)))
    for offset in range(0, len(registrations), 1000):
        db.session.execute(insert(Registration), registrations[offset:offset+1000])
    for offset in range(0, len(attendance), 1000):
        db.session.execute(insert(Attendance), attendance[offset:offset+1000])
    db.session.execute(insert(CancellationRequest), cancellations)
    db.session.execute(insert(Notification), [dict(user_id=person.id, title='Benchmark update', message='Disposable notification',
        is_read=i % 2 == 0) for i in range(100) for person in people[:50]])
    db.session.execute(insert(HistoricalActivity), [dict(source_key=f'benchmark:{i}',
        source_document='Disposable benchmark', source_page=1, source_row=i,
        title=f'Historical benchmark {i}', unit_name=campuses[i % 9].name, campus_id=campuses[i % 9].id,
        year_conducted=2025, volunteer_count=30) for i in range(500)])
    for kind in ('AOP', 'ASP'):
        plan = AnnualPlan(source_key=f'benchmark:{kind}', year=now.year, plan_type=kind,
                          title='Benchmark annual plan', source_document='Disposable benchmark')
        db.session.add(plan)
        db.session.flush()
        for campus in [None, *campuses]:
            code = str(campus.id) if campus else 'university'
            for basis in (('activities', 'verified_attendance') if kind == 'AOP' else ('unique_attendees',)):
                key = f'benchmark:{code}:{basis}'
                indicator = AnnualIndicator(source_key=key, plan=plan, code=key, name=basis,
                    program='Benchmark outreach', unit='count', responsible_office='Extension', evidence_basis=basis)
                target = AnnualTarget(source_key=key, indicator=indicator, campus_id=campus.id if campus else None,
                                      target_value=50, deadline=date(now.year, 12, 31))
                db.session.add(target)
                db.session.flush()
                db.session.execute(insert(AnnualActivityMapping), [dict(target_id=target.id, event_id=activity['id'])
                    for activity in activities if campus is None or activity['campus_id'] == campus.id])
    db.session.commit()
    return dict(activities=activity_count, registrations=len(registrations), attendance=len(attendance),
                volunteers=len(people), annual_goals=30)
