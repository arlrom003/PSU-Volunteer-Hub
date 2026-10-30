"""Explicit, transactional replacement of the isolated presentation dataset."""
import os
import random
from datetime import datetime, timedelta
from secrets import token_urlsafe

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import or_

from app.models import db
from app.models.audit import AuditLog
from app.models.event import (Attendance, CancellationRequest, Campus, Event,
                              ExternalParticipant, Registration, RecommendationLog,
                              SdgGoal)
from app.models.notification import Notification
from app.models.user import Interest, Skill, User, VolunteerProfile


DEMO_SERVICE_ID = '5ba9ae8d-fdd4-4850-a193-dcb5760a6e72'
PREFIX = '[Demo Dataset]'
KEEP = {'student@psu.edu': 'volunteer', 'coordinator@psu.edu': 'coordinator',
        'director@psu.edu': 'director'}
FIRST_NAMES = ('Andrea', 'Miguel', 'Camille', 'Paolo', 'Nicole', 'Rafael',
               'Bianca', 'Gabriel', 'Sofia', 'Adrian', 'Isabel', 'Marco',
               'Alyssa', 'Daniel', 'Patricia', 'Luis', 'Sam', 'Alex', 'Jamie',
               'Robin', 'Chris', 'Taylor', 'Francis', 'Angel', 'Jules')
LAST_NAMES = ('Reyes', 'Santos', 'Cruz', 'Garcia', 'Mendoza', 'Ramos', 'Torres',
              'Flores', 'Rivera', 'Aquino', 'Castillo', 'Navarro', 'Villanueva',
              'Bautista', 'Dela Cruz', 'Gonzales', 'Fernandez', 'Lopez', 'Perez',
              'Santiago', 'Domingo', 'Valdez', 'Aguilar', 'Mercado', 'Soriano',
              'Velasco', 'Rosales', 'Salazar', 'De Leon', 'Morales', 'Pascual',
              'Gutierrez', 'Padilla', 'Marquez', 'Dizon', 'Tolentino', 'Lim',
              'Tan', 'Cortez', 'Del Rosario')
ACTIVITIES = (
    ('Community Reading Partners', 'Education & Literacy', (4, 10)),
    ('Coastal Habitat Cleanup', 'Environment', (13, 14)),
    ('Community Wellness Outreach', 'Health & Wellness', (3, 10)),
    ('Digital Literacy Workshop', 'Technology & Digital', (4, 9)),
    ('Community Garden Project', 'Community Development', (2, 11)),
    ('Disaster Preparedness Workshop', 'Disaster Response', (11, 13)),
    ('Local Heritage Learning Day', 'Arts & Culture', (4, 11)),
    ('Youth Sports and Wellness', 'Sports & Recreation', (3, 16)),
    ('Riverbank Restoration', 'Environment', (6, 15)),
    ('Numeracy Mentoring Circle', 'Education & Literacy', (4, 10)),
    ('Food Security Outreach', 'Community Development', (1, 2)),
    ('Accessible Technology Clinic', 'Technology & Digital', (9, 10)),
)


def _name(index):
    return f'{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[index // len(FIRST_NAMES) % len(LAST_NAMES)]}'


def _old_records():
    events = Event.query.filter(or_(Event.title.startswith('[Demo Analytics]'),
                                    Event.title.startswith(PREFIX))).all()
    externals = ExternalParticipant.query.filter(
        ExternalParticipant.id_number.startswith('DEMO-EXT-')).all()
    event_ids = {event.id for event in events}
    for participant in externals:
        if any(r.event_id not in event_ids for r in participant.registrations):
            raise click.ClickException('A demo external participant also has non-demo registrations; no changes made.')
    return events, externals


def _replace_dataset(accounts, campuses, now):
    """All changes share the caller's transaction; no DDL or intermediate commits."""
    events, externals = _old_records()
    event_ids = [event.id for event in events]
    Notification.query.filter(Notification.related_event_id.in_(event_ids)).delete(synchronize_session=False)
    RecommendationLog.query.filter(RecommendationLog.event_id.in_(event_ids)).delete(synchronize_session=False)
    # Delete attendance before ORM registration cascades, including on SQLite.
    Attendance.query.filter(Attendance.event_id.in_(event_ids)).delete(synchronize_session=False)
    for event in events:
        db.session.delete(event)
    db.session.flush()
    for participant in externals:
        db.session.expire(participant, ['registrations'])
        db.session.delete(participant)
    AuditLog.query.filter_by(action='synthetic_demo_fixture').delete(synchronize_session=False)
    db.session.flush()

    from app import _seed_interests_skills, _seed_sdgs
    _seed_interests_skills(current_app, commit=False)
    _seed_sdgs(current_app, commit=False)
    skills = {skill.name: skill for skill in Skill.query.all()}
    interests = {interest.name: interest for interest in Interest.query.all()}
    sdgs = {goal.number: goal for goal in SdgGoal.query.all()}
    affiliations = ('College of Arts and Sciences', 'College of Education',
                    'College of Engineering', 'College of Business and Public Administration',
                    'College of Computing', 'College of Agriculture',
                    'College of Nursing', 'College of Hospitality Management')
    rng = random.Random(20261030)
    existing = {user.email: user for user in User.query.filter(
        User.email.endswith('@demo.invalid')).all()}

    def user_for(email, index, role, campus):
        user = existing.get(email)
        if user is not None and (user.role != role or user.id_number != f'SYN-{index:05d}'):
            raise click.ClickException(f'Fixture identity collision for {email}; no changes committed.')
        if user is None:
            user = User(name=_name(index), email=email, role=role,
                        id_number=f'SYN-{index:05d}', campus_id=campus.id,
                        sex=rng.choice(('male', 'female', 'prefer_not_to_say')),
                        created_at=now - timedelta(days=800),
                        college_affiliation=affiliations[index % len(affiliations)],
                        volunteer_type=('student', 'faculty', 'staff')[index % 3])
            # Synthetic identities cannot sign in with a shared demo password.
            user.set_password(token_urlsafe(32))
            db.session.add(user)
            if role == 'volunteer':
                user.profile = VolunteerProfile()
                category = ACTIVITIES[index % len(ACTIVITIES)][1]
                user.interests = [interests[category]]
                user.skills = [skills[name] for name in current_app.config['INTEREST_SKILL_MAP'][category]]
        return user

    coordinator = accounts['coordinator@psu.edu']
    if coordinator.campus_id not in {campus.id for campus in campuses}:
        coordinator.campus = campuses[0]
    coordinators = {coordinator.campus_id: coordinator}
    for index, campus in enumerate(campuses):
        if campus.id not in coordinators:
            coordinators[campus.id] = user_for(f'coordinator-{campus.id}@demo.invalid',
                                               1000 + index, 'coordinator', campus)
    student = accounts['student@psu.edu']
    if student.campus_id not in {campus.id for campus in campuses}:
        student.campus = campuses[0]
    if student.profile is None:
        student.profile = VolunteerProfile()
    volunteers = [student] + [user_for(f'volunteer-{index:04d}@demo.invalid', index,
                                     'volunteer', campuses[index % len(campuses)])
                              for index in range(1, 750)]
    external = []
    for index in range(200):
        participant = ExternalParticipant(id_number=f'DEMO-EXT-{index + 1:04d}',
            name=_name(index + 750), email=f'external-{index + 1:04d}@demo.invalid',
            sex=rng.choice(('male', 'female', 'prefer_not_to_say')),
            created_at=now - timedelta(days=800))
        db.session.add(participant)
        external.append(participant)
    db.session.flush()

    request_count = attendance_count = 0
    for index in range(200):
        title, category, goals = ACTIVITIES[index % len(ACTIVITIES)]
        campus = campuses[index % len(campuses)]
        past = index < 165
        full = not past and index >= 175 and index % 5 == 0
        date = (now - timedelta(days=2 + index * 4) if past
                else now + timedelta(days=2 + (index - 165) * 2))
        date = date.replace(hour=8, minute=0, second=0, microsecond=0)
        skill_names = current_app.config['INTEREST_SKILL_MAP'][category]
        event = Event(title=f'{PREFIX} {title}: {campus.name} {index + 1:03d}',
            description=(f'Volunteers will support {title.lower()} through guided community '
                         'activities, small-group assistance and a closing review. '
                         'Please arrive 15 minutes before the scheduled start.'),
            date=date, end_date=date + timedelta(hours=4),
            cancellation_deadline=date - timedelta(days=1), category=category,
            location=f'{campus.name} community activity area', campus=campus,
            slots=25 if full else (0 if index % 13 == 0 else (25 if index % 10 == 0 else 40)),
            target_participants=(None, 15, 20, 30)[index % 4],
            created_by=coordinators[campus.id],
            nda_required=index % 11 == 0,
            nda_text='Demonstration confidentiality agreement: keep participant details private.' if index % 11 == 0 else None,
            nda_version='demo-1' if index % 11 == 0 else None,
            participation_agreement_text='Demonstration participation agreement: follow activity instructions and report safety concerns.',
            participation_agreement_version='demo-1')
        event.required_skills_rel = [skills[name] for name in skill_names]
        event.sdgs = [sdgs[number] for number in (*goals, 17)]
        db.session.add(event)
        db.session.flush()
        for seat in range(25):
            user = volunteers[(index * 20 + seat) % len(volunteers)] if seat < 20 else None
            participant = external[(index * 5 + seat - 20) % 200] if seat >= 20 else None
            registered = min(now - timedelta(days=1), date - timedelta(days=7))
            registration = Registration(event=event, user=user,
                external_participant=participant, status='confirmed',
                registered_at=registered, policy_accepted_at=registered,
                policy_version='demo-1', nda_accepted_at=registered if event.nda_required else None,
                nda_version=event.nda_version,
                external_privacy_accepted_at=registered if participant else None,
                external_privacy_version='demo-1' if participant else None)
            db.session.add(registration)
            if past and (index < 159 or (index == 159 and seat < 15)
                         or (index == 160 and seat < 10)):
                attendance_status = 'present' if seat < (12, 18, 23)[index % 3] else ('absent' if seat % 2 else 'excused')
                registration.status = 'completed'
                db.session.add(Attendance(registration=registration, event=event,
                                          user=user, status=attendance_status))
                attendance_count += 1
            elif not past and user and request_count < 150:
                state = ('pending', 'approved', 'rejected')[request_count % 3]
                requested = min(now - timedelta(hours=4), date - timedelta(days=2))
                if state == 'approved':
                    registration.status = 'cancelled'
                db.session.add(CancellationRequest(registration=registration,
                    reason='Other', details='A scheduling conflict prevents participation.',
                    status=state, requested_at=requested,
                    reviewed_at=requested + timedelta(hours=1) if state != 'pending' else None,
                    reviewed_by=coordinators[campus.id] if state != 'pending' else None,
                    review_note='Demonstration review decision.' if state != 'pending' else None))
                request_count += 1
            elif not past and not full and seat % 7 == 0:
                registration.status = 'pending'
            if user:
                db.session.add(Notification(user=user, event=event,
                    title='Activity registration recorded', message=f'Your registration for {title} is recorded.',
                    notification_type='demo_fixture', created_at=registered))
        db.session.add(AuditLog(actor=coordinators[campus.id],
            action='synthetic_demo_fixture', target_type='event', target_id=event.id,
            details='Synthetic presentation fixture generated by reset-and-seed-demo.',
            created_at=date - timedelta(days=10)))
    db.session.flush()
    return attendance_count, request_count


@click.command('reset-and-seed-demo')
@click.option('--database', required=True, help='Exact configured demo database name.')
@click.option('--dry-run', is_flag=True, help='Inspect target and counts without writing.')
@with_appcontext
def reset_and_seed_demo(database, dry_run):
    """Replace marked demo records, preserving existing accounts and passwords."""
    if not current_app.testing and os.environ.get('RAILWAY_SERVICE_ID') != DEMO_SERVICE_ID:
        raise click.ClickException('Run only in the approved Railway demo application service.')
    if database != db.engine.url.database:
        raise click.ClickException('Database name does not match; no changes made.')
    accounts = {email: User.query.filter_by(email=email).first() for email in KEEP}
    for email, role in KEEP.items():
        if accounts[email] is None or accounts[email].role != role:
            raise click.ClickException(f'Required existing account {email} must have role {role}.')
    campuses = Campus.query.order_by(Campus.name).all()
    if not campuses:
        raise click.ClickException('Campus catalogue is empty; no changes made.')
    events, externals = _old_records()
    target = f'{db.engine.url.host or "local"}/{database}'
    click.echo(f'Target: {target}')
    click.echo(f'Replace {len(events)} marked demo events and {len(externals)} demo external participants; keep all existing login accounts/passwords.')
    click.echo(f'Create fixture: 750 volunteers, {len(campuses)} campuses, 200 events, 5000 registrations, 4000 attendance, 200 external participants, 150 cancellation requests.')
    if dry_run:
        db.session.rollback()
        return
    if click.prompt(f'Type RESET DEMO {target} to confirm backup and replacement') != f'RESET DEMO {target}':
        raise click.ClickException('Confirmation did not match; no changes made.')
    try:
        attendance, requests = _replace_dataset(accounts, campuses, datetime.now())
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    click.echo(f'Created 200 events, 5000 registrations, {attendance} attendance, 200 external participants, {requests} cancellation requests. Existing passwords preserved.')
