"""
Events Routes for PSU Volunteer Hub
=====================================
Manages event listings, registrations, and the volunteer dashboard.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, current_app)
from flask_login import login_required, current_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models import db
from app.models.user import VolunteerProfile
from app.models.event import (Event, Registration, Attendance, Campus,
                             ExternalParticipant, CancellationRequest)
from app.models.policy import ParticipationAgreementRevision
from app.recommendation.engine import get_recommendations, bootstrap_from_event
from app.utils.decorators import role_required
from app.models.notification import notify, notify_campus_coordinators
from app.utils.audit import log_activity
from datetime import datetime
from calendar import Calendar

events_bp = Blueprint('events', __name__, url_prefix='')

CANCELLATION_REASONS = (
    'Medical / Health Reason', 'Family Emergency', 'Academic Conflict',
    'Work / Schedule Conflict', 'Transportation Problem',
    'Personal Emergency', 'Other',
)
EXTERNAL_LINK_MAX_AGE = 60 * 60 * 24 * 30


def _listing_query():
    """Carry only existing listing filters, never a caller-supplied return URL."""
    return {key: request.args.getlist(key)
            for key in ('page', 'search', 'category', 'campus', 'campus_mode')
            if key in request.args}


def _registration_query():
    return {key: request.args.getlist(key)
            for key in ('status', 'campus', 'category', 'start_date', 'end_date',
                        'show', 'calendar_year', 'calendar_month')
            if key in request.args}


def _cancellation_state(registration, now=None):
    deadline = registration.event.cancellation_deadline or registration.event.date
    cancellation = registration.cancellation_request
    if cancellation:
        if cancellation.status == 'pending':
            code = 'pending'
            message = 'Your cancellation request is awaiting coordinator review.'
            if registration.status in ('pending', 'confirmed'):
                message += ' Your registration remains active until approval.'
        else:
            code = cancellation.status
            message = 'One cancellation request is allowed per registration. Another request is unavailable.'
            if cancellation.status == 'approved' and registration.status != 'cancelled':
                message = 'Your previous cancellation was approved, and you joined again. ' + message
    elif registration.status == 'cancelled':
        code, message = 'cancelled', 'This registration is cancelled.'
    elif registration.status not in ('pending', 'confirmed'):
        code, message = 'status', 'Only pending or confirmed registrations can request cancellation.'
    elif registration.attendance_record is not None:
        code, message = 'attendance', 'Cancellation is unavailable because attendance has been recorded.'
    elif deadline <= (now or datetime.now()):
        code, message = 'deadline', 'The cancellation deadline has passed.'
    else:
        code, message = 'available', 'You can request cancellation before the deadline. Coordinator approval is required.'
    return {'can_request': code == 'available', 'code': code,
            'message': message, 'deadline': deadline}


def _opportunity_state(event, registration=None, now=None):
    remaining = event.slots_remaining()
    if registration is not None and registration.status != 'cancelled':
        code, label = 'registered', 'Registered'
    elif event.date <= (now or datetime.now()):
        code, label = 'closed', 'Registration closed'
    elif event.slots > 0 and remaining <= 0:
        code, label = 'full', 'Full'
    else:
        code, label = 'available', 'Open for joining'
    return {'code': code, 'label': label, 'remaining': remaining}


def _agreement_for(event):
    if event.participation_agreement_text:
        return {'title': 'Event Participation Agreement',
                'body': event.participation_agreement_text,
                'version': event.participation_agreement_version or 'event'}
    revision = ParticipationAgreementRevision.query.filter_by(
        is_active=True).order_by(ParticipationAgreementRevision.published_at.desc()).first()
    return ({'title': revision.title, 'body': revision.body, 'version': revision.version}
            if revision else {
                'title': 'Event Participation Agreement',
                'version': 'system-default',
                'body': ('By joining this activity, I commit to participate, follow PSU '
                         'guidelines, and submit a cancellation request if I cannot attend.'),
            })


def _external_token(registration):
    serializer = URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'], salt='external-registration')
    return serializer.dumps({'registration_id': registration.id})


def _external_registration_from_token(token):
    serializer = URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'], salt='external-registration')
    payload = serializer.loads(token, max_age=EXTERNAL_LINK_MAX_AGE)
    registration_id = payload.get('registration_id') if isinstance(payload, dict) else None
    registration = db.session.get(Registration, registration_id)
    if registration is None or not registration.is_external:
        raise BadSignature('Unknown external registration')
    return registration


def _external_cancellation_available(registration):
    event = registration.event
    return (
        registration.status in ('pending', 'confirmed')
        and registration.attendance_record is None
        and (event.cancellation_deadline or event.date) > datetime.now()
        and not (registration.cancellation_request
                 and registration.cancellation_request.status == 'pending')
    )


def _upsert_external_participant(id_number, name=None, contact_number=None,
                                 address=None, email=None, sex=None):
    """Find an existing outsider by ID number or create a new record."""
    id_number = (id_number or '').strip()
    participant = ExternalParticipant.query.filter_by(id_number=id_number).first()
    if participant is None:
        participant = ExternalParticipant(id_number=id_number)
        db.session.add(participant)
    # Optional fields: populate when provided, never overwrite with blanks.
    if name and not participant.name:
        participant.name = name.strip()
    if contact_number and not participant.contact_number:
        participant.contact_number = contact_number.strip()
    if address and not participant.address:
        participant.address = address.strip()
    if email and not participant.email:
        participant.email = email.strip()
    if sex and not participant.sex:
        participant.sex = sex
    db.session.flush()
    return participant


@events_bp.route('/opportunities')
def opportunities():
    page = request.args.get('page', 1, type=int)
    per_page = 9
    campuses = Campus.query.order_by(func.lower(Campus.name), Campus.name, Campus.id).all()
    available_campuses = {campus.id for campus in campuses}
    raw_campuses = [value.strip() for value in request.args.getlist('campus') if value.strip()]
    requested_campuses = request.args.getlist('campus', type=int)
    selected_campuses = set(requested_campuses) & available_campuses
    campus_mode = request.args.get('campus_mode', 'include')
    filter_error = None
    if len(requested_campuses) != len(raw_campuses) or not set(requested_campuses) <= available_campuses:
        filter_error = 'Some campus choices are unavailable. Choose campuses from the list and apply filters again.'
    if campus_mode not in ('include', 'exclude'):
        filter_error = 'Choose whether to show only or exclude the selected campuses, then apply filters again.'
        campus_mode = 'include'
    category = (request.args.get('category', type=str) or '').strip() or None
    search = (request.args.get('search', type=str) or '').strip() or None
    now = datetime.now()
    query = Event.query.filter(Event.date >= now, Event.slots > 0)
    upcoming_count = query.count()
    if filter_error:
        query = query.filter(db.false())
    elif selected_campuses:
        if campus_mode == 'exclude':
            query = query.filter(db.or_(Event.campus_id.is_(None),
                                       Event.campus_id.notin_(selected_campuses)))
        else:
            query = query.filter(Event.campus_id.in_(selected_campuses))
    if category:
        query = query.filter(Event.category == category)
    if search:
        like = f'%{search}%'
        query = query.filter(Event.title.ilike(
            like) | Event.description.ilike(like))
    query = query.order_by(Event.date.asc(), Event.id.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    events = pagination.items
    # Data-driven category filter: distinct categories actually in use,
    # so the dropdown never offers options that return zero results.
    categories = [row[0] for row in db.session.query(
        Event.category).distinct().order_by(Event.category).all() if row[0]]
    registrations_by_event = {}
    if current_user.is_authenticated and current_user.role == 'volunteer':
        registrations_by_event = {
            registration.event_id: registration
            for registration in Registration.query.filter_by(
                user_id=current_user.id).all()
            if registration.status != 'cancelled'
        }
    return render_template('volunteer/Volunteer_opportunities.html',
                           events=events, campuses=campuses,
                           categories=categories,
                           current_page=pagination.page,
                           total_pages=pagination.pages,
                           total_count=pagination.total,
                           selected_campuses=sorted(selected_campuses),
                           campus_mode=campus_mode,
                           filter_error=filter_error,
                           selected_category=category,
                           selected_status='upcoming',
                           search_query=search,
                           registered_event_ids=set(registrations_by_event),
                           opportunity_states={event.id: _opportunity_state(
                               event, registrations_by_event.get(event.id), now)
                               for event in events},
                           listing_query=_listing_query(), upcoming_count=upcoming_count,
                           has_filters=bool(search or category or raw_campuses or filter_error),
                           first_result=(pagination.page - 1) * per_page + 1 if pagination.total else 0,
                           last_result=min(pagination.page * per_page, pagination.total)), 400 if filter_error else 200


@events_bp.route('/opportunities/<int:event_id>')
def opportunity_detail(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    registration = None
    if current_user.is_authenticated and current_user.role == 'volunteer':
        registration = Registration.query.filter_by(
            user_id=current_user.id, event_id=event.id).first()
    return render_template(
        'events/opportunity_detail.html', event=event, registration=registration,
        opportunity_state=_opportunity_state(event, registration),
        listing_query=_listing_query())


@events_bp.route('/opportunities/register/<int:event_id>', methods=['GET', 'POST'])
@login_required
@role_required('volunteer')
def register_for_event(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    listing_query = _listing_query()
    details_url = url_for('events.opportunity_detail', event_id=event.id, **listing_query)
    if event.date <= datetime.now():
        flash('This activity has already started and cannot accept registrations.', 'error')
        return redirect(details_url)
    agreement = _agreement_for(event)
    if agreement is None:
        flash('This activity cannot accept registrations until its participation agreement is published.', 'error')
        return redirect(details_url)
    existing = Registration.query.filter_by(
        user_id=current_user.id, event_id=event_id).first()
    if existing and existing.status != 'cancelled':
        flash('You are already registered for this event.', 'warning')
        return redirect(details_url)
    if event.slots > 0 and event.slots_remaining() <= 0:
        flash('No available slots for this event.', 'error')
        return redirect(details_url)
    errors = {}
    accepted_agreement = request.method == 'POST' and request.form.get('accept_agreement') == 'yes'
    accepted_nda = request.method == 'POST' and request.form.get('accept_nda') == 'yes'
    if request.method == 'POST':
        if not accepted_agreement:
            errors['accept_agreement'] = 'Accept the Participation Agreement to join.'
        if event.nda_required and not accepted_nda:
            errors['accept_nda'] = 'Accept the Non-Disclosure Agreement to join.'
    if request.method == 'GET' or errors:
        return render_template(
            'events/registration_consent.html', event=event, agreement=agreement,
            external=False, errors=errors, accepted_agreement=accepted_agreement,
            accepted_nda=accepted_nda, listing_query=listing_query), 400 if errors else 200
    if existing:
        existing.status = 'confirmed'
        existing.policy_accepted_at = datetime.utcnow()
        existing.policy_version = agreement['version']
        existing.nda_accepted_at = datetime.utcnow() if event.nda_required else None
        existing.nda_version = event.nda_version if event.nda_required else None
        registration = existing
        success_message = f'Your registration has been restored for {event.title}.'
    else:
        registration = Registration(user_id=current_user.id, event_id=event_id,
            status='confirmed', policy_accepted_at=datetime.utcnow(),
            policy_version=agreement['version'],
            nda_accepted_at=datetime.utcnow() if event.nda_required else None,
            nda_version=event.nda_version if event.nda_required else None)
        db.session.add(registration)
        success_message = f'You have joined {event.title}. Your registration is confirmed.'
    db.session.flush()
    log_activity('participation_agreement_accepted', registration,
                 {'event_id': event.id, 'version': agreement['version']})
    if event.nda_required:
        log_activity('nda_accepted', registration, {'event_id': event.id, 'version': event.nda_version})
    db.session.commit()
    bootstrap_from_event(current_user, event)
    notify_campus_coordinators(
        event.campus_id,
        title=f'New registration: {event.title}',
        message=f'{current_user.name or current_user.email} registered for '
                f'"{event.title}".',
        notification_type='registration',
        related_event_id=event.id)
    db.session.commit()
    flash(success_message, 'success')
    return redirect(details_url)


@events_bp.route('/registrations/<int:registration_id>/cancel', methods=['GET', 'POST'])
@login_required
@role_required('volunteer')
def cancel_registration(registration_id):
    """Request review of a future signup cancellation; never cancel directly."""
    registration = db.session.get(Registration, registration_id)
    if registration is None:
        abort(404)
    if registration.user_id != current_user.id:
        abort(403)
    event = registration.event
    dashboard_query = _registration_query()
    dashboard_url = url_for('events.volunteer_dash', _anchor=f'registration-{registration.id}', **dashboard_query)
    state = _cancellation_state(registration)
    if not state['can_request']:
        flash(state['message'], 'warning')
        return redirect(dashboard_url)
    reason = request.form.get('reason', '').strip() if request.method == 'POST' else ''
    details = request.form.get('details', '').strip() if request.method == 'POST' else ''
    errors = {}
    if request.method == 'POST':
        if reason not in CANCELLATION_REASONS:
            errors['reason'] = 'Choose a cancellation reason.'
        if reason == 'Other' and not details:
            errors['details'] = 'Explain your reason when choosing Other.'
    if request.method == 'GET' or errors:
        return render_template('events/cancellation_request.html', registration=registration,
                               event=event, cancellation_state=state, dashboard_query=dashboard_query,
                               dashboard_url=dashboard_url, reasons=CANCELLATION_REASONS,
                               selected_reason=reason, submitted_details=details, errors=errors), 400 if errors else 200
    cancellation = CancellationRequest(registration_id=registration.id,
                                       reason=reason, details=details or None)
    try:
        db.session.add(cancellation)
        db.session.flush()
        log_activity('cancellation_requested', cancellation,
                     {'event_id': event.id, 'reason': reason})
        notify_campus_coordinators(
            event.campus_id,
            title=f'Cancellation request: {event.title}',
            message=f'{current_user.name or current_user.email} requested cancellation for "{event.title}".',
            notification_type='cancellation_requested',
            related_event_id=event.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not CancellationRequest.query.filter_by(registration_id=registration.id).first():
            raise
        flash('A cancellation request already exists for this registration. Review its status below.', 'warning')
        return redirect(dashboard_url)
    flash(f'Your cancellation request for {event.title} was sent for coordinator review. Your registration remains active until approval.', 'success')
    return redirect(dashboard_url)


@events_bp.route('/volunteer_dash')
@login_required
@role_required('volunteer')
def volunteer_dash():
    profile = VolunteerProfile.query.filter_by(user_id=current_user.id).first()
    upcoming_events = Event.query.filter(
        Event.date >= datetime.now()).order_by(Event.date.asc()).all()
    recommendations = get_recommendations(
        profile, upcoming_events, campus_id=current_user.campus_id)
    total_activities = Registration.query.filter_by(
        user_id=current_user.id).count()
    cert_level = 'Active' if total_activities else 'New'
    user_stats = {'total_activities': total_activities, 'cert_level': cert_level}
    now = datetime.now()
    upcoming = Registration.query.filter_by(user_id=current_user.id).join(Event).filter(
        Event.date >= now, Registration.status.in_(('pending', 'confirmed'))
    ).order_by(Event.date.asc()).limit(5).all()
    recent_activity = Registration.query.filter_by(user_id=current_user.id).order_by(
        Registration.registered_at.desc()).limit(5).all()
    registrations = Registration.query.filter_by(user_id=current_user.id).join(Event).all()
    upcoming_registrations = [r for r in registrations if (
        r.status in ('pending', 'confirmed') and r.event.date > now)]
    history_registrations = [r for r in registrations if r not in upcoming_registrations]
    upcoming_registrations.sort(key=lambda r: r.event.date)
    history_registrations.sort(
        key=lambda r: r.registered_at or datetime.min, reverse=True)
    status_filter = request.args.get('status', '').strip()
    campus_filter = request.args.get('campus', type=int)
    category_filter = request.args.get('category', '').strip()
    start_filter = request.args.get('start_date', '').strip()
    end_filter = request.args.get('end_date', '').strip()
    filtered_registrations = registrations
    if status_filter:
        filtered_registrations = [r for r in filtered_registrations if r.status == status_filter]
    if campus_filter:
        filtered_registrations = [r for r in filtered_registrations if r.event.campus_id == campus_filter]
    if category_filter:
        filtered_registrations = [r for r in filtered_registrations if r.event.category == category_filter]
    try:
        if start_filter:
            start = datetime.fromisoformat(start_filter)
            filtered_registrations = [r for r in filtered_registrations if r.event.date >= start]
        if end_filter:
            end = datetime.fromisoformat(end_filter).replace(hour=23, minute=59, second=59)
            filtered_registrations = [r for r in filtered_registrations if r.event.date <= end]
    except ValueError:
        flash('Use valid dates for registration history filters.', 'error')
    filtered_registrations.sort(key=lambda r: r.registered_at or datetime.min, reverse=True)
    shown = max(5, request.args.get('show', 5, type=int) or 5)
    shown = min(shown, len(filtered_registrations))
    registration_items = [
        {
            'registration': r,
            'cancellation_state': _cancellation_state(r, now),
            'cancellation_status': r.cancellation_request.status if r.cancellation_request else None,
        }
        for r in filtered_registrations[:shown]]
    year = request.args.get('calendar_year', now.year, type=int) or now.year
    month = request.args.get('calendar_month', now.month, type=int) or now.month
    if month < 1 or month > 12:
        year, month = now.year, now.month
    active_calendar = [r for r in upcoming_registrations if r.status == 'confirmed']
    events_by_day = {}
    for registration in active_calendar:
        if registration.event.date.year == year and registration.event.date.month == month:
            events_by_day.setdefault(registration.event.date.day, []).append(registration)
    calendar_weeks = Calendar(firstweekday=0).monthdayscalendar(year, month)
    previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    campuses = Campus.query.order_by(Campus.name).all()
    categories = sorted({r.event.category for r in registrations if r.event.category})
    upcoming_schedule = [{'event': r.event, 'date': r.event.date}
                         for r in upcoming]
    certification = {'level': cert_level}
    return render_template('volunteer/Volunteer_dash.html',
                           recommendations=recommendations,
                           user_stats=user_stats,
                           recent_activity=recent_activity,
                           registration_items=registration_items,
                           registration_total=len(filtered_registrations), shown_registrations=shown,
                           has_registrations=bool(registrations), dashboard_query=_registration_query(),
                           registration_filters={'status': status_filter, 'campus': campus_filter,
                                                 'category': category_filter, 'start_date': start_filter,
                                                 'end_date': end_filter},
                           campuses=campuses, categories=categories,
                           calendar_year=year, calendar_month=month,
                           calendar_month_name=datetime(year, month, 1).strftime('%B %Y'),
                           calendar_weeks=calendar_weeks, calendar_events=events_by_day,
                           previous_calendar=(previous_year, previous_month),
                           next_calendar=(next_year, next_month),
                           upcoming_schedule=upcoming_schedule,
                           certification=certification)


def _dismiss_first_use_guide():
    current_user.first_use_guide_dismissed_at = datetime.utcnow()
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json':
        return {'dismissed': True}
    dashboards = {
        'volunteer': 'events.volunteer_dash',
        'coordinator': 'coordinator.coordinator_dash',
        'director': 'director.director_dash',
        'admin': 'admin.admin_dash',
    }
    return redirect(url_for(dashboards.get(current_user.role, 'events.volunteer_dash')))


@events_bp.route('/guide/dismiss', methods=['POST'])
@login_required
def dismiss_first_use_guide():
    """Persist an authenticated user's decision to skip or finish the guide."""
    return _dismiss_first_use_guide()


@events_bp.route('/volunteer_dash/guide/dismiss', methods=['POST'])
@login_required
@role_required('volunteer')
def dismiss_volunteer_first_use_guide():
    """Compatibility route for the former volunteer-only guide."""
    return _dismiss_first_use_guide()


@events_bp.route('/event/<int:event_id>/join', methods=['GET', 'POST'])
def event_join(event_id):
    """Redirect retired public join links to the PSU sign-in flow."""
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    return redirect(url_for(
        'auth.login', next=url_for('events.register_for_event', event_id=event.id)))


@events_bp.route('/external/registrations/<token>')
def external_registration_manage(token):
    """Show a guest only the registration represented by their signed link."""
    try:
        registration = _external_registration_from_token(token)
    except (BadSignature, SignatureExpired):
        return render_template('events/external_registration_unavailable.html'), 404
    return render_template(
        'events/external_registration_manage.html',
        registration=registration,
        token=token,
        can_cancel=_external_cancellation_available(registration),
        reasons=CANCELLATION_REASONS,
    )


@events_bp.route('/external/registrations/<token>/cancel', methods=['POST'])
def external_registration_cancel(token):
    """Accept a signed guest cancellation request for coordinator review."""
    try:
        registration = _external_registration_from_token(token)
    except (BadSignature, SignatureExpired):
        return render_template('events/external_registration_unavailable.html'), 404
    if not _external_cancellation_available(registration):
        flash('Cancellation is unavailable because the deadline passed or a request is already pending.',
              'error')
        return redirect(url_for('events.external_registration_manage', token=token))
    reason = request.form.get('reason', '').strip()
    details = request.form.get('details', '').strip()
    if reason not in CANCELLATION_REASONS or (reason == 'Other' and not details):
        flash('Choose a cancellation reason. Explain Other reasons.', 'error')
        return redirect(url_for('events.external_registration_manage', token=token))
    cancellation = CancellationRequest(
        registration_id=registration.id,
        reason=reason,
        details=details or None,
    )
    db.session.add(cancellation)
    db.session.flush()
    log_activity('cancellation_requested', cancellation,
                 {'event_id': registration.event_id, 'reason': reason,
                  'external': True})
    db.session.commit()
    notify_campus_coordinators(
        registration.event.campus_id,
        title=f'Cancellation request: {registration.event.title}',
        message=(f'{registration.external_participant.name or "External volunteer"} '
                 f'requested cancellation for "{registration.event.title}".'),
        notification_type='cancellation_requested',
        related_event_id=registration.event_id,
    )
    db.session.commit()
    flash('Your cancellation request was sent for coordinator review.', 'success')
    return redirect(url_for('events.external_registration_manage', token=token))
