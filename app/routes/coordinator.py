"""
Coordinator Routes for PSU Volunteer Hub
==========================================
Manages event creation, attendance tracking, and coordinator dashboard.
"""
import os
import uuid
import zipfile
from calendar import Calendar
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response, abort, send_from_directory
from flask_login import login_required, current_user
from app.models import db
from app.models.event import (ActivityCategory, Event, EventAnnouncement,
                              Registration, Attendance, Campus, Milestone,
                              CancellationRequest, SdgGoal)
from app.utils.decorators import role_required, roles_required
from app.models.notification import Notification, notify_campus_coordinators
from app.models.notification import notify
from app.utils.audit import log_activity
from app.models.user import SystemSetting
from app.recommendation.analytics import AnalyticsAggregator
from app.dashboard import summarize_report
from app.reports import (
    build_events_report, render_csv, render_pdf, ReportError, parse_date_range)
from datetime import datetime, timedelta

coordinator_bp = Blueprint('coordinator', __name__, url_prefix='')

EVENT_COVER_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
EVENT_COVER_MAX_BYTES = 5 * 1024 * 1024
MILESTONE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'pdf', 'docx'}


def _max_event_slots():
    setting = SystemSetting.query.filter_by(key='max_slots_per_event').first()
    try:
        return max(1, int(setting.value)) if setting else 100
    except (TypeError, ValueError):
        return 100


def _activity_categories():
    """Return valid categories even while a fresh database is being seeded.

    The configured category list is the application-level source of truth. The
    database table lets administrators extend it, but an empty lookup table
    must not prevent coordinators from creating or editing activities.
    """
    configured = current_app.config.get('EVENT_CATEGORIES', [])
    stored = [
        category.name
        for category in ActivityCategory.query.order_by(
            ActivityCategory.name,
        ).all()
    ]
    return list(dict.fromkeys([*configured, *stored, 'General']))


def _selected_sdgs(form):
    """Resolve submitted SDG ids against the server-side catalogue."""
    ids = [int(value) for value in form.getlist('sdg_ids') if value.isdigit()]
    return SdgGoal.query.filter(SdgGoal.id.in_(ids)).order_by(SdgGoal.number).all() if ids else []


def _activity_form_context(**context):
    context.setdefault('categories', _activity_categories())
    context.setdefault('sdgs', SdgGoal.query.order_by(SdgGoal.number).all())
    context.setdefault('max_slots', _max_event_slots())
    return context


def _attendance_state(event, now):
    """Describe the current attendance action for an event without changing it."""
    opens_at = event.date - timedelta(minutes=30)
    ends_at = event.end_date or event.date
    if now < opens_at:
        return {
            'kind': 'locked',
            'label': 'Check-in Opens',
            'time': opens_at,
        }
    if now >= ends_at:
        return {
            'kind': 'final',
            'label': 'Final Attendance Due',
            'time': ends_at,
        }
    return {
        'kind': 'active',
        'label': 'Check-in Active',
        'time': ends_at,
    }


def _save_event_cover(file):
    if not file or not file.filename:
        return None
    extension = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
    if extension not in EVENT_COVER_EXTENSIONS:
        raise ValueError('Cover image must be JPEG, PNG, or WebP.')
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > EVENT_COVER_MAX_BYTES:
        raise ValueError('Cover image must be 5 MB or smaller.')
    try:
        with Image.open(file.stream) as image:
            detected = (image.format or '').lower()
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError('Cover image is not a valid image file.')
    finally:
        file.stream.seek(0)
    valid_formats = {'jpeg': {'jpg', 'jpeg'}, 'png': {'png'}, 'webp': {'webp'}}
    if extension not in valid_formats.get(detected, set()):
        raise ValueError('Cover image extension does not match its contents.')
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'events')
    os.makedirs(upload_dir, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.{extension}'
    file.save(os.path.join(upload_dir, filename))
    return {
        'path': f'uploads/events/{filename}',
        'original_name': secure_filename(file.filename),
    }


def _validate_milestone(file):
    """Validate content, not just the user-controlled filename extension."""
    extension = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
    if extension not in MILESTONE_EXTENSIONS:
        raise ValueError('Milestones must be JPEG, PNG, WebP, PDF, or DOCX files.')
    file.stream.seek(0, os.SEEK_END)
    if file.stream.tell() > current_app.config['MILESTONE_MAX_BYTES']:
        raise ValueError('Milestone files must be 10 MB or smaller.')
    file.stream.seek(0)
    if extension in {'jpg', 'jpeg', 'png', 'webp'}:
        try:
            with Image.open(file.stream) as image:
                detected = (image.format or '').lower()
                image.verify()
        except (UnidentifiedImageError, OSError):
            raise ValueError('Milestone image is not valid.')
        allowed_extensions = {'jpg', 'jpeg'} if detected == 'jpeg' else {detected}
        if extension not in allowed_extensions:
            raise ValueError('Milestone filename does not match its image content.')
    elif extension == 'pdf' and not file.stream.read(5).startswith(b'%PDF-'):
        raise ValueError('Milestone file is not a valid PDF.')
    elif extension == 'docx' and not zipfile.is_zipfile(file.stream):
        raise ValueError('Milestone file is not a valid DOCX.')
    file.stream.seek(0)
    return extension


def _coordinator_campus_id():
    """Coordinator campus scope is always derived server-side, never from the
    request, so a forged ?campus_id= parameter cannot leak another campus."""
    campus_id = current_user.campus_id
    if not campus_id:
        abort(403)
    return campus_id


def _parse_event_schedule(form):
    """Parse activity dates and derive its cancellation deadline from days."""
    try:
        start = datetime.fromisoformat(form.get('date', '').strip())
        end_raw = form.get('end_date', '').strip()
        end = datetime.fromisoformat(end_raw) if end_raw else None
    except ValueError:
        return None, 'Enter valid activity dates and times.'
    days_raw = form.get('cancellation_days', '2').strip()
    try:
        cancellation_days = int(days_raw)
    except ValueError:
        return None, 'Enter whole days before the activity for cancellations.'
    if not 0 <= cancellation_days <= 365:
        return None, 'Cancellation must close from 0 to 365 days before the activity.'
    deadline = start - timedelta(days=cancellation_days)
    if end and end <= start:
        return None, 'The end date and time must be after the start.'
    return (start, end, deadline), None


@coordinator_bp.route('/coordinator_dash')
@login_required
@role_required('coordinator')
def coordinator_dash():
    status = request.args.get('status', 'upcoming')
    category = request.args.get('category', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    events = Event.query.filter_by(campus_id=current_user.campus_id)
    if status == 'upcoming':
        events = events.filter(Event.date >= datetime.now())
    elif status == 'completed':
        events = events.filter(Event.date < datetime.now())
    elif status == 'cancelled':
        events = events.join(Registration).filter(Registration.status == 'cancelled')
    if category:
        events = events.filter(Event.category == category)
    for value, column in ((start_date, 'start'), (end_date, 'end')):
        if value:
            try:
                date_value = datetime.fromisoformat(value)
                events = events.filter(Event.date >= date_value if column == 'start'
                                       else Event.date <= date_value.replace(hour=23, minute=59, second=59))
            except ValueError:
                flash('Use valid dates when filtering activities.', 'error')
    events = events.order_by(Event.date.desc()).all()
    upcoming_count = sum(1 for e in events if e.date >= datetime.now())
    # Centralized campus-scoped participation metrics (Phase 18): keeps the
    # dashboard consistent with the analytics page, CSV and PDF exports.
    summary = AnalyticsAggregator.participation_summary(
        campus_id=current_user.campus_id)
    accomplishments = AnalyticsAggregator.activity_accomplishments(
        campus_id=current_user.campus_id, start_date=start_date,
        end_date=end_date, category=category, limit=None)
    visible_event_ids = {event.id for event in events}
    accomplishments = [row for row in accomplishments
                       if row['event'].id in visible_event_ids]
    pending_cancellations = CancellationRequest.query.join(Registration).join(Event).filter(
        Event.campus_id == current_user.campus_id,
        CancellationRequest.status == 'pending').count()
    recent_activities = Registration.query.filter(
        Registration.event_id.in_([e.id for e in events])
    ).order_by(Registration.registered_at.desc()).limit(5).all() if events else []

    # Context the template needs but the route was not passing
    campus_name = current_user.campus.name if current_user.campus else 'Campus'

    return render_template('coordinator/Coordinator_dash.html',
                            events=events,
                            upcoming_count=upcoming_count,
                            total_volunteers=summary['unique_volunteers'],
                            attendance_rate=summary['attendance_rate'],
                            registrations=summary['registrations'],
                            recent_activities=recent_activities,
                            selected_status=status,
                            selected_category=category, start_date=start_date,
                            end_date=end_date, categories=_activity_categories(),
                            accomplishments=accomplishments,
                            pending_cancellations=pending_cancellations,
                            campus_name=campus_name,
                            campus_total_attended=summary['attended'])


@coordinator_bp.route('/coordinator/calendar')
@login_required
@role_required('coordinator')
def activity_calendar():
    now = datetime.now()
    year = request.args.get('year', now.year, type=int) or now.year
    month = request.args.get('month', now.month, type=int) or now.month
    if not 1 <= month <= 12:
        year, month = now.year, now.month
    events = Event.query.filter_by(campus_id=current_user.campus_id).filter(
        db.extract('year', Event.date) == year,
        db.extract('month', Event.date) == month).order_by(Event.date).all()
    by_day = {}
    for event in events:
        by_day.setdefault(event.date.day, []).append(event)
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    following = (year + 1, 1) if month == 12 else (year, month + 1)
    return render_template('coordinator/activity_calendar.html',
                           calendar_weeks=Calendar(firstweekday=0).monthdayscalendar(year, month),
                           calendar_events=by_day,
                           calendar_month=datetime(year, month, 1).strftime('%B %Y'),
                           previous_calendar=previous, next_calendar=following)


@coordinator_bp.route('/coordinator/cancellation-requests', methods=['GET', 'POST'])
@login_required
@role_required('coordinator')
def cancellation_requests():
    status = request.args.get('status', 'pending')
    query = CancellationRequest.query.join(Registration).join(Event).filter(
        Event.campus_id == current_user.campus_id)
    if status in ('pending', 'approved', 'rejected'):
        query = query.filter(CancellationRequest.status == status)
    if request.method == 'POST':
        cancellation = db.session.get(CancellationRequest, request.form.get('request_id', type=int))
        decision = request.form.get('decision')
        note = request.form.get('review_note', '').strip()
        if cancellation is None or cancellation.registration.event.campus_id != current_user.campus_id:
            abort(403)
        if cancellation.status != 'pending' or decision not in ('approved', 'rejected'):
            flash('This request is no longer available for review.', 'error')
        else:
            cancellation.status = decision
            cancellation.reviewed_by_id = current_user.id
            cancellation.reviewed_at = datetime.utcnow()
            cancellation.review_note = note or None
            if decision == 'approved':
                cancellation.registration.status = 'cancelled'
            db.session.flush()
            log_activity(f'cancellation_{decision}', cancellation,
                         {'event_id': cancellation.registration.event_id})
            if cancellation.registration.user_id:
                notify(cancellation.registration.user_id,
                       title=f'Cancellation request {decision}',
                       message=f'Your request for "{cancellation.registration.event.title}" was {decision}.',
                       notification_type=f'cancellation_{decision}',
                       related_event_id=cancellation.registration.event_id)
            db.session.commit()
            flash(f'Cancellation request {decision}.', 'success')
        return redirect(url_for('coordinator.cancellation_requests', status=status))
    return render_template('coordinator/cancellation_requests.html',
                           requests=query.order_by(CancellationRequest.requested_at.desc()).all(),
                           selected_status=status)


@coordinator_bp.route('/create_activity', methods=['GET', 'POST'])
@login_required
@role_required('coordinator')
def create_activity():
    campuses = [current_user.campus] if current_user.campus else []
    categories = _activity_categories()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('date', '').strip()
        location = request.form.get('location', '').strip()
        required_skills = request.form.get('required_skills', '').strip()
        category = request.form.get('category', 'General').strip()
        slots = request.form.get('slots', 0, type=int)
        target_participants = request.form.get('target_participants', type=int)
        agreement_text = request.form.get('participation_agreement_text', '').strip()
        agreement_version = request.form.get('participation_agreement_version', '').strip()
        nda_required = request.form.get('nda_required') == 'on'
        nda_text = request.form.get('nda_text', '').strip()
        nda_version = request.form.get('nda_version', '').strip()
        max_slots = _max_event_slots()
        campus_id = current_user.campus_id
        if campus_id is None:
            flash('Your account must be assigned to a campus before creating activities.', 'error')
            return render_template('coordinator/create_act_scrn1.html', **_activity_form_context(campuses=campuses))
        if not title or not description or not date_str:
            flash('Title, description, and date are required.', 'error')
            return render_template('coordinator/create_act_scrn1.html', **_activity_form_context(campuses=campuses))
        if category not in categories:
            flash('Select a valid activity category.', 'error')
            return render_template('coordinator/create_act_scrn1.html',
                                   campuses=campuses, categories=categories,
                                   max_slots=max_slots)
        sdgs = _selected_sdgs(request.form)
        if SdgGoal.query.count() and not sdgs:
            flash('Select at least one Sustainable Development Goal.', 'error')
            return render_template('coordinator/create_act_scrn1.html',
                                   **_activity_form_context(campuses=campuses))
        if slots < 1 or slots > max_slots:
            flash(f'Volunteer slots must be between 1 and {max_slots}.', 'error')
            return render_template('coordinator/create_act_scrn1.html',
                                   campuses=campuses, max_slots=max_slots)
        if target_participants is not None and target_participants < 1:
            flash('Target participants must be a positive number when provided.', 'error')
            return render_template('coordinator/create_act_scrn1.html', campuses=campuses,
                                   categories=categories, max_slots=max_slots)
        if (agreement_text and not agreement_version) or (nda_required and (not nda_text or not nda_version)):
            flash('Provide a version for a custom agreement and text/version for a required NDA.', 'error')
            return render_template('coordinator/create_act_scrn1.html', campuses=campuses,
                                   categories=categories, max_slots=max_slots)
        schedule, error = _parse_event_schedule(request.form)
        if error:
            flash(error, 'error')
            return render_template('coordinator/create_act_scrn1.html',
                                   campuses=campuses, categories=categories,
                                   max_slots=max_slots)
        date, end_date, cancellation_deadline = schedule
        try:
            cover = _save_event_cover(request.files.get('cover_image'))
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('coordinator/create_act_scrn1.html',
                                   campuses=campuses, max_slots=max_slots)
        event = Event(title=title, description=description, date=date,
                      end_date=end_date,
                      cancellation_deadline=cancellation_deadline,
                      category=category, location=location,
                      required_skills=required_skills, slots=slots,
                      target_participants=target_participants,
                      participation_agreement_text=agreement_text or None,
                      participation_agreement_version=agreement_version or None,
                      nda_required=nda_required, nda_text=nda_text or None,
                      nda_version=nda_version or None,
                      campus_id=campus_id,
                      created_by_id=current_user.id,
                      cover_image_path=cover['path'] if cover else None,
                      cover_image_name=cover['original_name'] if cover else None,
                      cover_uploaded_by_id=current_user.id if cover else None,
                      cover_uploaded_at=datetime.utcnow() if cover else None)
        db.session.add(event)
        event.sdgs = sdgs
        db.session.commit()
        flash('Activity created successfully!', 'success')
        return redirect(url_for('coordinator.coordinator_dash'))
    return render_template('coordinator/create_act_scrn1.html',
                           **_activity_form_context(campuses=campuses))


@coordinator_bp.route('/coordinator/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('coordinator')
def edit_activity(event_id):
    """Edit an activity owned by the coordinator's assigned campus.

    Campus ownership is enforced server-side: the event must belong to the
    coordinator's campus, otherwise 403. The campus is never changed by the
    edit (a submitted campus_id is ignored), so a coordinator cannot move an
    event to another campus. Capacity cannot be reduced below the number of
    existing registrations.
    """
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.campus_id != current_user.campus_id:
        abort(403)

    categories = _activity_categories()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('date', '').strip()
        location = request.form.get('location', '').strip()
        required_skills = request.form.get('required_skills', '').strip()
        category = request.form.get('category', 'General').strip()
        slots = request.form.get('slots', 0, type=int)
        target_participants = request.form.get('target_participants', type=int)
        agreement_text = request.form.get('participation_agreement_text', '').strip()
        agreement_version = request.form.get('participation_agreement_version', '').strip()
        nda_required = request.form.get('nda_required') == 'on'
        nda_text = request.form.get('nda_text', '').strip()
        nda_version = request.form.get('nda_version', '').strip()
        max_slots = _max_event_slots()

        if category not in categories:
            flash('Select a valid activity category.', 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   categories=categories, max_slots=max_slots)
        sdgs = _selected_sdgs(request.form)
        if SdgGoal.query.count() and not sdgs:
            flash('Select at least one Sustainable Development Goal.', 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   **_activity_form_context())
        if not title or not description or not date_str:
            flash('Title, description, and date are required.', 'error')
            return render_template('coordinator/edit_activity.html', event=event)
        schedule, error = _parse_event_schedule(request.form)
        if error:
            flash(error, 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   categories=categories, max_slots=max_slots)
        date, end_date, cancellation_deadline = schedule
        if slots < 1 or slots > max_slots:
            flash(f'Volunteer slots must be between 1 and {max_slots}.', 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   max_slots=max_slots)
        if target_participants is not None and target_participants < 1:
            flash('Target participants must be a positive number when provided.', 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   categories=categories, max_slots=max_slots)
        if (agreement_text and not agreement_version) or (nda_required and (not nda_text or not nda_version)):
            flash('Provide a version for a custom agreement and text/version for a required NDA.', 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   categories=categories, max_slots=max_slots)

        # Registration-sensitive: do not reduce capacity below existing
        # registrations (PSU + external). This preserves all participation.
        existing = Registration.query.filter_by(event_id=event.id).count()
        if slots < existing:
            flash(f'Cannot reduce slots below existing registrations ({existing}).',
                  'error')
            return render_template('coordinator/edit_activity.html', event=event)

        event.title = title
        event.description = description
        event.date = date
        event.end_date = end_date
        event.cancellation_deadline = cancellation_deadline
        event.location = location
        event.category = category
        event.required_skills = required_skills
        event.sdgs = sdgs
        event.slots = slots
        event.target_participants = target_participants
        event.participation_agreement_text = agreement_text or None
        event.participation_agreement_version = agreement_version or None
        event.nda_required = nda_required
        event.nda_text = nda_text or None
        event.nda_version = nda_version or None
        old_cover = event.cover_image_path
        try:
            cover = _save_event_cover(request.files.get('cover_image'))
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('coordinator/edit_activity.html', event=event,
                                   max_slots=max_slots)
        if cover:
            event.cover_image_path = cover['path']
            event.cover_image_name = cover['original_name']
            event.cover_uploaded_by_id = current_user.id
            event.cover_uploaded_at = datetime.utcnow()
        # campus_id is intentionally left unchanged (server-side ownership).
        db.session.commit()
        if cover and old_cover:
            old_path = os.path.join(current_app.static_folder, old_cover)
            if os.path.isfile(old_path):
                os.remove(old_path)
        flash('Activity updated successfully!', 'success')
        return redirect(url_for('coordinator.coordinator_dash'))

    return render_template('coordinator/edit_activity.html', event=event,
                           **_activity_form_context())


@coordinator_bp.route('/coordinator/events/<int:event_id>/delete', methods=['POST'])
@login_required
@role_required('coordinator')
def delete_activity(event_id):
    """Permanently remove a campus-owned event and notify PSU volunteers."""
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.campus_id != current_user.campus_id:
        abort(403)

    registrations = Registration.query.filter_by(event_id=event.id).all()
    affected_volunteers = [r.user_id for r in registrations if r.user_id is not None]
    for user_id in affected_volunteers:
        db.session.add(Notification(
            user_id=user_id,
            title=f'Activity cancelled: {event.title}',
            message=f'The activity "{event.title}" has been removed by its '
                    'coordinator. Your registration was cancelled.',
            notification_type='event_cancelled'))

    cover_path = event.cover_image_path
    registration_count = len(registrations)
    db.session.delete(event)
    db.session.commit()
    if cover_path:
        file_path = os.path.join(current_app.static_folder, cover_path)
        if os.path.isfile(file_path):
            os.remove(file_path)
    if registration_count:
        flash(f'Activity removed. {registration_count} registration(s) were cancelled.',
              'success')
    else:
        flash('Activity removed.', 'success')
    return redirect(url_for('coordinator.coordinator_dash'))


@coordinator_bp.route('/coordinator/events/<int:event_id>/announcements',
                      methods=['POST'])
@login_required
@role_required('coordinator')
def publish_announcement(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.campus_id != current_user.campus_id:
        abort(403)
    announcement_type = request.form.get('announcement_type', '').strip()
    message = request.form.get('message', '').strip()
    allowed = {'last_call', 'event_update', 'cancelled_postponed'}
    if announcement_type not in allowed or not message:
        flash('Select an announcement type and enter a message.', 'error')
        return redirect(url_for('coordinator.coordinator_dash'))
    if len(message) > 1000:
        flash('Announcement must be 1,000 characters or fewer.', 'error')
        return redirect(url_for('coordinator.coordinator_dash'))

    db.session.add(EventAnnouncement(
        event_id=event.id,
        author_id=current_user.id,
        announcement_type=announcement_type,
        message=message,
    ))
    registrations = Registration.query.filter(
        Registration.event_id == event.id,
        Registration.user_id.isnot(None),
        Registration.status.in_(('pending', 'confirmed')),
    ).all()
    for registration in registrations:
        db.session.add(Notification(
            user_id=registration.user_id,
            title=f'Activity update: {event.title}',
            message=message,
            notification_type=announcement_type,
            related_event_id=event.id,
        ))
    db.session.commit()
    flash(f'Announcement published to {len(registrations)} volunteer(s).',
          'success')
    return redirect(url_for('coordinator.coordinator_dash'))


@coordinator_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
@role_required('coordinator')
def attendance():
    events = Event.query.filter_by(
        campus_id=current_user.campus_id).order_by(Event.date.asc()).all()
    now = datetime.now()
    today_events = [event for event in events if event.date.date() == now.date()]
    future_events = [event for event in events if event.date.date() > now.date()][:3]
    quick_activities = [
        {'event': event, 'state': _attendance_state(event, now)}
        for event in [*today_events, *future_events]
    ]
    selected_event_id = request.args.get('event_id', type=int)
    selected_event = None
    registrations = []
    if selected_event_id:
        selected_event = Event.query.filter_by(
            id=selected_event_id, campus_id=current_user.campus_id).first()
        if selected_event is None:
            abort(403)
        registrations = Registration.query.filter(
            Registration.event_id == selected_event.id,
            Registration.status != 'cancelled',
        ).all()
    if request.method == 'POST':
        event_id = request.form.get('event_id', type=int)
        reg_ids = request.form.getlist('registration_id')
        statuses = request.form.getlist('status')
        selected_event = Event.query.filter_by(
            id=event_id, campus_id=current_user.campus_id).first()
        if selected_event is None:
            abort(403)
        try:
            registration_ids = [int(value) for value in reg_ids]
        except (TypeError, ValueError):
            abort(400)
        if len(registration_ids) != len(set(registration_ids)):
            abort(400)
        registrations_by_id = {
            registration.id: registration
            for registration in Registration.query.filter(
                Registration.id.in_(registration_ids or [-1]),
                Registration.event_id == selected_event.id,
            ).all()
        }
        if len(registrations_by_id) != len(registration_ids):
            abort(403)
        now = datetime.now()
        if now < selected_event.date - timedelta(minutes=30):
            flash('Check-in is not open yet. It opens 30 minutes before the activity starts.', 'error')
            return redirect(url_for('coordinator.attendance', event_id=selected_event.id))
        activity_ended = now >= (selected_event.end_date or selected_event.date)
        for i, reg_id in enumerate(reg_ids):
            reg = registrations_by_id[int(reg_id)]
            status = statuses[i] if i < len(statuses) else ''
            if not status:
                continue
            if status not in {'present', 'absent', 'excused'}:
                abort(400)
            reg.status = 'completed' if status == 'present' and activity_ended else 'confirmed'
            existing = Attendance.query.filter_by(
                registration_id=reg.id).first()
            if existing:
                existing.status = status
            else:
                db.session.add(Attendance(registration_id=reg.id, user_id=reg.user_id,
                               event_id=reg.event_id, status=status))
        db.session.commit()
        flash('Attendance updated successfully!' if activity_ended else
              'Check-in saved. Save final attendance after the activity ends to confirm completion and certificate eligibility.', 'success')
        return redirect(url_for('coordinator.attendance', event_id=event_id))
    attendance_opens_at = selected_event.date - timedelta(minutes=30) if selected_event else None
    attendance_counts = {'registered': len(registrations), 'present': 0,
                         'absent': 0, 'excused': 0, 'unmarked': 0}
    for registration in registrations:
        status = registration.attendance_record.status if registration.attendance_record else 'unmarked'
        attendance_counts[status] += 1
    return render_template('coordinator/attendance_MnGmt.html', events=events,
                           registrations=registrations, selected_event=selected_event,
                           quick_activities=quick_activities,
                           attendance_state=(_attendance_state(selected_event, now)
                                             if selected_event else None),
                           attendance_counts=attendance_counts,
                           attendance_opens_at=attendance_opens_at,
                           attendance_locked=bool(attendance_opens_at and now < attendance_opens_at),
                           activity_ended=bool(selected_event and now >= (selected_event.end_date or selected_event.date)))


@coordinator_bp.route('/events/<int:event_id>/milestones', methods=['POST'])
@login_required
@role_required('coordinator')
def upload_milestone(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.campus_id != current_user.campus_id:
        abort(403)
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('coordinator.coordinator_dash'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('coordinator.coordinator_dash'))
    category = request.form.get('category', 'photo')
    try:
        ext = _validate_milestone(file)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('coordinator.coordinator_dash'))
    upload_dir = os.path.join(current_app.config['PRIVATE_UPLOAD_FOLDER'], 'milestones')
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    milestone = Milestone(
        event_id=event.id,
        filename=secure_filename(file.filename),
        upload_path=f'milestones/{filename}',
        category=category,
        uploaded_by_id=current_user.id,
    )
    db.session.add(milestone)
    db.session.commit()
    flash('Milestone uploaded successfully!', 'success')
    return redirect(url_for('coordinator.coordinator_dash'))


@coordinator_bp.route('/milestones/<int:milestone_id>/download')
@login_required
@roles_required('coordinator', 'director', 'admin')
def download_milestone(milestone_id):
    """Serve new private milestone files only to authorized internal roles."""
    milestone = db.session.get(Milestone, milestone_id)
    if milestone is None:
        abort(404)
    if current_user.role == 'coordinator' and milestone.event.campus_id != current_user.campus_id:
        abort(403)
    if milestone.upload_path.startswith('uploads/'):
        abort(410)
    directory, filename = os.path.split(milestone.upload_path)
    return send_from_directory(
        os.path.join(current_app.config['PRIVATE_UPLOAD_FOLDER'], directory),
        filename, as_attachment=True, download_name=milestone.filename)


@coordinator_bp.route('/reports/events.csv')
@login_required
@role_required('coordinator')
def export_events_csv():
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    category = request.args.get('category', '').strip()
    try:
        rows, summary = build_events_report(
            campus_id=_coordinator_campus_id(), start_date=start_date,
            end_date=end_date, category=category,
            activity_name=request.args.get('activity_name', ''))
    except ReportError:
        abort(400)
    campus_name = current_user.campus.name if current_user.campus else 'Campus'
    meta = {
        'title': f'{campus_name} Campus Activity Report',
        'scope': f'{campus_name} Campus (Coordinator)',
        'date_range': _date_range_label(start_date, end_date),
        'category': category or 'All Categories',
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'role_label': 'Coordinator',
    }
    meta['activity_name'] = request.args.get('activity_name', '').strip()
    csv_data = render_csv(rows, summary, meta)
    return Response(csv_data, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment;filename=campus_events.csv'})


@coordinator_bp.route('/reports/events.pdf')
@login_required
@role_required('coordinator')
def export_events_pdf():
    from app.reports import _build_meta
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    category = request.args.get('category', '').strip()
    try:
        rows, summary = build_events_report(
            campus_id=_coordinator_campus_id(), start_date=start_date,
            end_date=end_date, category=category,
            activity_name=request.args.get('activity_name', ''))
    except ReportError:
        abort(400)
    campus_name = current_user.campus.name if current_user.campus else 'Campus'
    meta = _build_meta(
        title=f'{campus_name} Campus Activity Report',
        scope=f'{campus_name} Campus (Coordinator)',
        start_date=start_date, end_date=end_date, category=category,
        role_label='Coordinator')
    meta['activity_name'] = request.args.get('activity_name', '').strip()
    pdf_data = render_pdf(rows, summary, meta)
    return Response(pdf_data, mimetype='application/pdf', headers={
        'Content-Disposition': 'attachment;filename=campus_events.pdf'})


def _date_range_label(start_date, end_date):
    from app.reports import _date_range_label as _lbl
    return _lbl(start_date, end_date)


@coordinator_bp.route('/coordinator_analytics')
@login_required
@role_required('coordinator')
def analytics():
    campus_id = _coordinator_campus_id()
    try:
        parse_date_range(request.args.get('start_date'), request.args.get('end_date'))
    except ReportError:
        flash('Use valid report dates, with the start date on or before the end date.', 'error')
        return redirect(url_for('coordinator.analytics'))
    # All aggregations scoped to the coordinator's own campus so the page
    # reflects the coordinator's reality, not the whole university.
    campus_name = current_user.campus.name if current_user.campus else 'Campus'
    forecast_data = AnalyticsAggregator.forecast_turnout(
        campus_id=campus_id)
    attendance_summary = AnalyticsAggregator.attendance_summary(
        campus_id=campus_id)
    categories = [row[0] for row in db.session.query(Event.category).filter(
        Event.campus_id == campus_id,
        Event.category.isnot(None)).distinct().order_by(Event.category).all()]

    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    category = request.args.get('category', '').strip()
    report_rows, report_summary = build_events_report(
        campus_id=campus_id, start_date=start_date,
        end_date=end_date, category=category,
        activity_name=request.args.get('activity_name', ''))

    return render_template('coordinator/coordinator_analytics.html',
                            campus_name=campus_name,
                            forecast_data=forecast_data,
                            attendance_summary=attendance_summary,
                            categories=categories,
                            report_rows=report_rows,
                            report_summary=report_summary,
                            dashboard_data=summarize_report(report_rows))


# ── Outsider (External Volunteer) manual encoding ───────────────────────────────

@coordinator_bp.route('/coordinator/events/<int:event_id>/external', methods=['GET', 'POST'])
@login_required
@role_required('coordinator')
def add_external_participant(event_id):
    """Coordinators manually encode an outsider for one of their campus events."""
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.campus_id != current_user.campus_id:
        abort(403)

    if request.method == 'POST':
        id_number = request.form.get('id_number', '').strip()
        sex = request.form.get('sex', '').strip().lower() or None
        if not id_number:
            flash('ID number is required for outsider registration.', 'error')
            return render_template(
                'coordinator/add_external.html', event=event), 400
        if sex not in (None, 'male', 'female', 'prefer_not_to_say'):
            flash('Choose a valid gender response.', 'error')
            return render_template('coordinator/add_external.html', event=event), 400
        from app.models.event import Registration
        from app.routes.events import _upsert_external_participant
        participant = _upsert_external_participant(
            id_number,
            name=request.form.get('name', '').strip(),
            contact_number=request.form.get('contact_number', '').strip(),
            address=request.form.get('address', '').strip(),
            email=request.form.get('email', '').strip(), sex=sex)
        existing = Registration.query.filter_by(
            external_participant_id=participant.id, event_id=event.id).first()
        if existing is None:
            db.session.add(Registration(
                external_participant_id=participant.id, event_id=event.id,
                status='confirmed'))
            db.session.commit()
            notify_campus_coordinators(
                event.campus_id,
                title=f'New external volunteer: {event.title}',
                message=f'An external volunteer ({participant.name or participant.id_number}) '
                        f'was added to "{event.title}" by a coordinator.',
                notification_type='external_registration',
                related_event_id=event.id)
            db.session.commit()
        flash('External volunteer added to the activity.', 'success')
        return redirect(url_for('coordinator.attendance', event_id=event.id))

    return render_template('coordinator/add_external.html', event=event)
