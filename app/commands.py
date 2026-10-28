"""Flask CLI commands for importing institutional historical data."""
import csv
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext
from email_validator import validate_email, EmailNotValidError
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta

from app.models import db
from app.models.event import (Campus, HistoricalActivity, Event, Registration,
                              Attendance, ExternalParticipant, SdgGoal)
from app.models.user import User


@click.command('init-production')
@click.option('--database', required=True, help='Exact name of the empty database already created by the operator.')
@with_appcontext
def init_production(database):
    """Initialize an EMPTY database with reference data and one administrator."""
    if current_app.config.get('APP_ENV') != 'production':
        raise click.ClickException('Use production configuration: flask --app wsgi:app init-production.')
    if not database or database != db.engine.url.database:
        raise click.ClickException('Database name does not match the configured target; no changes made.')
    inspector = inspect(db.engine)
    if inspector.get_table_names() or inspector.get_view_names():
        raise click.ClickException('Database is not empty. Refusing initialization; use reviewed migrations for existing databases.')
    click.echo(f'Target: {db.engine.url.host or "local"} / {database}')
    click.confirm('Create the schema, reference data, and first Admin in this empty database?', abort=True)
    name = click.prompt('Admin name').strip()
    email = click.prompt('Admin email').strip()
    if not name or len(name) > 100:
        raise click.ClickException('Admin name must contain 1 to 100 characters.')
    try:
        email = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        raise click.ClickException('Enter a valid administrator email address.') from None
    if len(email) > 120:
        raise click.ClickException('Admin email must be at most 120 characters.')
    password = click.prompt('Admin password (at least 12 characters)', hide_input=True, confirmation_prompt=True)
    if len(password) < 12 or not password.strip():
        raise click.ClickException('Administrator password must contain at least 12 characters.')
    administrator = User(name=name, email=email, role='admin')
    administrator.set_password(password)
    # Only run once, offline: MariaDB/MySQL schema DDL cannot be rolled back.
    from app import _seed_campuses, _seed_interests_skills, _seed_sdgs
    try:
        db.create_all()
        _seed_campuses(current_app, commit=False)
        _seed_interests_skills(current_app, commit=False)
        _seed_sdgs(current_app, commit=False)
        db.session.add(administrator)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise click.ClickException('Initialization failed. Schema may remain; inspect it manually before any recovery. No automatic retry or table deletion performed.') from None
    click.echo('Production initialized: reference data and one Admin; no demo users or activities.')


def _optional_int(value, field, line_number):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise click.ClickException(
            f'Invalid {field} on CSV line {line_number}: {value!r}') from exc


@click.command('import-historical-activities')
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False,
                                             path_type=Path))
@click.option('--dry-run', is_flag=True,
              help='Validate and report changes without committing them.')
@with_appcontext
def import_historical_activities(csv_path, dry_run):
    """Idempotently import aggregate historical activities from CSV."""
    required = {
        'source_key', 'source_document', 'source_page', 'source_row',
        'unit_name', 'title', 'activity_type', 'partners',
        'participant_categories', 'volunteer_count', 'year_conducted',
    }
    campuses = {c.name.casefold(): c for c in Campus.query.all()}
    aliases = {'sta. maria': 'santa maria'}
    created = updated = unchanged = 0

    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise click.ClickException(
                f'Missing CSV columns: {", ".join(sorted(missing))}')

        for line_number, row in enumerate(reader, start=2):
            source_key = row['source_key'].strip()
            title = row['title'].strip()
            unit_name = row['unit_name'].strip()
            if not source_key or not title or not unit_name:
                raise click.ClickException(
                    f'CSV line {line_number} requires source_key, unit_name, and title')

            campus_key = unit_name.removesuffix(' Campus').strip().casefold()
            campus = campuses.get(aliases.get(campus_key, campus_key))
            values = {
                'source_document': row['source_document'].strip(),
                'source_page': _optional_int(row['source_page'], 'source_page', line_number),
                'source_row': _optional_int(row['source_row'], 'source_row', line_number),
                'unit_name': unit_name,
                'campus_id': campus.id if campus else None,
                'title': title,
                'activity_type': row['activity_type'].strip() or None,
                'partners': row['partners'].strip() or None,
                'participant_categories': row['participant_categories'].strip() or None,
                'volunteer_count': _optional_int(row['volunteer_count'], 'volunteer_count', line_number),
                'year_conducted': _optional_int(row['year_conducted'], 'year_conducted', line_number),
            }
            item = HistoricalActivity.query.filter_by(source_key=source_key).first()
            if item is None:
                db.session.add(HistoricalActivity(source_key=source_key, **values))
                created += 1
            elif any(getattr(item, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(item, key, value)
                updated += 1
            else:
                unchanged += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    click.echo(
        f'{"Dry run: " if dry_run else ""}{created} created, '
        f'{updated} updated, {unchanged} unchanged.')


@click.command('seed-demo-analytics')
@with_appcontext
def seed_demo_analytics():
    """Create idempotent demo registrations and attendance for presentations."""
    prefix = '[Demo Analytics]'
    volunteers = User.query.filter_by(role='volunteer').order_by(User.id).all()
    campuses = Campus.query.order_by(Campus.id).limit(4).all()
    if not volunteers or not campuses:
        raise click.ClickException('Seed campuses and volunteer users first.')

    now = datetime.now()
    definitions = [
        ('Community Food Drive', 'Community', 1, 7, 4),
        ('Green Campus Initiative', 'Environment', 2, 6, 5),
        ('Youth Coding Mentor', 'Technology', 3, 5, 3),
        ('Rural Literacy Program', 'Education', 4, 4, 2),
        ('Coastal Cleanup Drive', 'Environment', 5, 8, 7),
        ('Community Wellness Fair', 'Health', 6, 3, 2),
    ]
    extra_categories = [
        ('Tree Growing Day', 'Environment'),
        ('Reading Buddies', 'Education'),
        ('Digital Skills Clinic', 'Technology'),
        ('Barangay Health Caravan', 'Health'),
        ('Nutrition Pack Distribution', 'Community'),
        ('Riverbank Restoration', 'Environment'),
        ('Math Mentoring Day', 'Education'),
        ('Computer Basics Workshop', 'Technology'),
        ('Wellness Screening', 'Health'),
        ('Relief Goods Packing', 'Community'),
        ('Coastal Habitat Survey', 'Environment'),
        ('Youth Tutoring Circle', 'Education'),
        ('Online Safety Seminar', 'Technology'),
        ('First Aid Orientation', 'Health'),
        ('Community Garden Build', 'Community'),
        ('Mangrove Stewardship', 'Environment'),
        ('Library Learning Lab', 'Education'),
        ('Device Repair Clinic', 'Technology'),
    ]
    definitions.extend(
        (title, category, index + 1, 10 + index * 8,
         3 + (index * 3) % 10)
        for index, (title, category) in enumerate(extra_categories)
    )
    created_events = created_registrations = created_attendance = 0
    created_external = created_external_registrations = 0
    for title, category, campus_offset, days_ago, registration_count in definitions:
        campus = campuses[(campus_offset - 1) % len(campuses)]
        event = Event.query.filter_by(title=f'{prefix} {title}').first()
        if event is None:
            event = Event(
                title=f'{prefix} {title}',
                description='Presentation data for PSU Volunteer Hub analytics.',
                date=now - timedelta(days=days_ago),
                category=category,
                required_skills='Communication, Teamwork',
                slots=max(registration_count, 10),
                campus_id=campus.id)
            db.session.add(event)
            db.session.flush()
            created_events += 1
        sdgs = SdgGoal.query.order_by(SdgGoal.number).all()
        if sdgs:
            event.sdgs = [sdgs[event.id % len(sdgs)], sdgs[(event.id + 4) % len(sdgs)]]
        for index in range(registration_count):
            volunteer = volunteers[index % len(volunteers)]
            registration = Registration.query.filter_by(
                user_id=volunteer.id, event_id=event.id).first()
            if registration is None:
                registration = Registration(
                    user_id=volunteer.id, event_id=event.id, status='confirmed')
                db.session.add(registration)
                db.session.flush()
                created_registrations += 1
            if index < max(1, registration_count - 1):
                attendance = Attendance.query.filter_by(
                    registration_id=registration.id).first()
                if attendance is None:
                    db.session.add(Attendance(
                        registration_id=registration.id,
                        user_id=volunteer.id,
                        event_id=event.id,
                        status='present'))
                    registration.status = 'completed'
                    created_attendance += 1

    external_data = [
        ('DEMO-EXT-001', 'Alex Reyes', 'male'),
        ('DEMO-EXT-002', 'Maria Santos', 'female'),
        ('DEMO-EXT-003', 'Jordan Cruz', 'prefer_not_to_say'),
        ('DEMO-EXT-004', 'Lea Garcia', 'female'),
    ]
    external_participants = []
    for id_number, name, sex in external_data:
        participant = ExternalParticipant.query.filter_by(id_number=id_number).first()
        if participant is None:
            participant = ExternalParticipant(
                id_number=id_number, name=name,
                email=f'{id_number.lower()}@demo.invalid', sex=sex)
            db.session.add(participant)
            db.session.flush()
            created_external += 1
        external_participants.append(participant)

    for index, participant in enumerate(external_participants):
        event = Event.query.filter_by(title=f'{prefix} {definitions[index][0]}').first()
        registration = Registration.query.filter_by(
            external_participant_id=participant.id, event_id=event.id).first()
        if registration is None:
            registration = Registration(
                external_participant_id=participant.id,
                event_id=event.id, status='confirmed')
            db.session.add(registration)
            db.session.flush()
            created_external_registrations += 1
        if index < 3 and not Attendance.query.filter_by(registration_id=registration.id).first():
            db.session.add(Attendance(
                registration_id=registration.id, event_id=event.id,
                status='present' if index != 2 else 'excused'))
            registration.status = 'completed'
            created_attendance += 1
    db.session.commit()
    click.echo(
        f'{created_events} events, {created_registrations} registrations, '
        f'{created_attendance} attendance records, {created_external} external '
        f'participants, and {created_external_registrations} external registrations created.')


def register_commands(app):
    app.cli.add_command(init_production)
    app.cli.add_command(import_historical_activities)
    app.cli.add_command(seed_demo_analytics)
