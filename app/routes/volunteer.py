"""
Volunteer Profile Routes for PSU Volunteer Hub
===============================================
Handles profile viewing/editing, participation history, and
profile-level analytics (impact stats, badges, level progress,
preferred categories, and event recommendations).
"""
from collections import Counter
from datetime import datetime, timedelta
import os
import uuid
from pathlib import Path

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, session)
from flask_login import login_required, current_user
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from app.models import db
from app.models.user import (VolunteerProfile, Skill, Interest, User,
                             AuthSecurityEvent, PasswordResetToken)
from app.models.event import Registration, Event, Attendance
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from app.recommendation.engine import get_recommendations
from app.utils.decorators import role_required
from app.utils.audit import log_activity
from app.campuses import campus_rows, campus_affiliations, official_campus
from app.security import password_error, password_min_length
from app.services.session_idle import end_session

volunteer_bp = Blueprint('volunteer', __name__, url_prefix='')


def _selected_records(model, values):
    if not values:
        raise ValueError('Select at least one choice.')
    if any(not str(value).isascii() or not str(value).isdigit() for value in values):
        raise ValueError('Choose only the available options.')
    ids = {int(value) for value in values}
    records = model.query.filter(model.id.in_(ids)).all()
    if len(records) != len(ids):
        raise ValueError('An option is no longer available. Review your choices.')
    return records


def _delete_profile_image(path):
    if not path:
        return
    directory = (Path(current_app.static_folder) / 'uploads' / 'profiles').resolve()
    target = (Path(current_app.static_folder) / path).resolve()
    if target.parent != directory:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning('Could not remove profile image: %s', target)


def _save_profile_image(file):
    if not file or not file.filename:
        return None
    extension = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
    if extension not in {'jpg', 'jpeg', 'png', 'webp'}:
        raise ValueError('Profile image must be JPEG, PNG, or WebP.')
    file.stream.seek(0, os.SEEK_END)
    if file.stream.tell() > 3 * 1024 * 1024:
        raise ValueError('Profile image must be 3 MB or smaller.')
    file.stream.seek(0)
    try:
        with Image.open(file.stream) as image:
            if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValueError('Profile image must be JPEG, PNG, or WebP.')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('Profile image is not a valid image file.')
    finally:
        file.stream.seek(0)
    directory = os.path.join(current_app.static_folder, 'uploads', 'profiles')
    os.makedirs(directory, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.{extension}'
    path = f'uploads/profiles/{filename}'
    try:
        file.save(os.path.join(directory, filename))
    except OSError:
        _delete_profile_image(path)
        raise
    return path


def _level_progress(total_activities):
    """Compute volunteer progress from completed participation counts."""
    tiers = [
        ('Bronze', 'Newcomer', 0, 3),
        ('Silver', 'Active Volunteer', 3, 10),
        ('Gold', 'Community Leader', 10, 20),
        ('Platinum', 'Champion', 20, None),
    ]
    for cert, label, low, high in tiers:
        if high is None or total_activities < high:
            if high is None:
                return {'cert_level': cert, 'label': label, 'percent': 100}
            percent = round(((total_activities - low) / (high - low)) * 100, 1)
            return {
                'cert_level': cert, 'label': label,
                'percent': max(0.0, min(percent, 100.0)),
            }


def _compute_badges(total_activities, distinct_categories):
    """Derive earned badges from actual participation data."""
    badges = [
        {'name': 'Helping Hand', 'icon': 'volunteer_activism',
            'earned': total_activities >= 1},
        {'name': 'Active Volunteer', 'icon': 'diversity_3', 'earned': total_activities >= 5},
        {'name': 'Category Explorer', 'icon': 'travel_explore',
            'earned': distinct_categories >= 3},
        {'name': 'Community Champion', 'icon': 'star', 'earned': total_activities >= 15},
    ]
    return badges


def _preferred_categories(user_id, top_n=3):
    """Most frequent event categories among the user's attended events."""
    rows = db.session.query(Event.category).join(
        Attendance, Attendance.event_id == Event.id
    ).filter(Attendance.user_id == user_id, Attendance.status == 'present').all()
    counts = Counter(r[0] for r in rows if r[0])
    return [name for name, _ in counts.most_common(top_n)]


@volunteer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('volunteer')
def profile_page():
    errors = {}
    selected_skills = [str(skill.id) for skill in current_user.skills]
    selected_interests = [str(interest.id) for interest in current_user.interests]

    if request.method == 'POST':
        selected_skills = request.form.getlist('skills')
        selected_interests = request.form.getlist('interests')
        selections = {}
        for name, model, values in (
            ('skills', Skill, selected_skills),
            ('interests', Interest, selected_interests),
        ):
            try:
                selections[name] = _selected_records(model, values)
            except ValueError as exc:
                errors[name] = str(exc)
        image = request.files.get('profile_image')
        image_path = None
        if not errors:
            try:
                image_path = _save_profile_image(image)
            except ValueError as exc:
                errors['profile_image'] = str(exc)
            except OSError:
                current_app.logger.exception('Profile photo upload failed')
                errors['profile_image'] = 'Photo could not be saved. Choose it again and retry.'
        if not errors:
            old_path = current_user.profile_image_path
            try:
                profile = VolunteerProfile.query.filter_by(user_id=current_user.id).first()
                if not profile:
                    profile = VolunteerProfile(user_id=current_user.id)
                    db.session.add(profile)
                current_user.skills = selections['skills']
                current_user.interests = selections['interests']
                if image_path:
                    current_user.profile_image_path = image_path
                    current_user.profile_image_name = secure_filename(image.filename)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                _delete_profile_image(image_path)
                current_app.logger.exception('Profile save failed')
                errors['save'] = 'Profile was not saved. Please retry. If you chose a photo, choose it again.'
            else:
                if image_path:
                    _delete_profile_image(old_path)
                flash('Profile updated successfully!', 'success')
                return redirect(url_for('volunteer.profile_page'))

    return _render_profile(errors=errors, selected_skills=selected_skills,
                           selected_interests=selected_interests, status=422 if errors else 200)


def _render_profile(errors=None, selected_skills=None, selected_interests=None,
                    account_section=None, account_errors=None, account_values=None, status=200):
    profile = VolunteerProfile.query.filter_by(user_id=current_user.id).first()
    if selected_skills is None:
        selected_skills = [str(skill.id) for skill in current_user.skills]
    if selected_interests is None:
        selected_interests = [str(interest.id) for interest in current_user.interests]
    values = dict(name=current_user.name, campus_id=str(current_user.campus_id or ''),
                  college_affiliation=current_user.college_affiliation or '')
    values.update(account_values or {})
    campuses = campus_rows()
    # ── Analytics: impact stats ─────────────────────────────────────────
    total_activities = Registration.query.filter_by(
        user_id=current_user.id).count()

    verified_attendance = Attendance.query.filter_by(
        user_id=current_user.id, status='present').count()
    completed_participation = Registration.query.join(
        Registration.attendance_record
    ).filter(Registration.user_id == current_user.id,
             Registration.status == 'completed', Attendance.status == 'present').count()
    level = _level_progress(completed_participation)

    distinct_categories = db.session.query(Event.category).join(
        Attendance, Attendance.event_id == Event.id
    ).filter(Attendance.user_id == current_user.id, Attendance.status == 'present')\
     .distinct().count()

    badges = _compute_badges(completed_participation, distinct_categories)
    preferred_categories = _preferred_categories(current_user.id)

    user_stats = {
        'total_activities': total_activities,
        'verified_attendance': verified_attendance,
        'completed_participation': completed_participation,
        'cert_level': level['cert_level'],
        'level_label': level['label'],
        'level_percent': level['percent'],
    }

    # ── Analytics: registration history (for the table on this page) ───
    registrations = Registration.query.filter_by(user_id=current_user.id)\
        .options(joinedload(Registration.event), joinedload(Registration.attendance_record))\
        .order_by(Registration.registered_at.desc()).limit(5).all()

    # ── Analytics: cosine-similarity recommendations ────────────────────
    recommendations_error = None
    try:
        recommendations = get_recommendations(
            profile, top_n=3, campus_id=current_user.campus_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Profile recommendations unavailable')
        recommendations = []
        recommendations_error = 'Recommendations could not be loaded. Please retry later.'

    return render_template(
        'volunteer/Volunteer_Profile.html',
        profile=profile,
        user_stats=user_stats,
        badges=badges,
        preferred_categories=preferred_categories,
        registrations=registrations,
        recommendations=recommendations,
        recommendations_error=recommendations_error,
        errors=errors or {},
        account_section=account_section,
        account_errors=account_errors or {},
        account_values=values,
        campuses=campuses,
        affiliation_options={str(campus.id): campus_affiliations(campus) for campus in campuses},
        password_min=password_min_length(),
        selected_skills=selected_skills,
        selected_interests=selected_interests,
        skill_catalog=Skill.query.order_by(Skill.name).all(),
        interest_catalog=Interest.query.order_by(Interest.name).all(),
    ), status


def _account_failure(section, errors, values=None, status=422):
    return _render_profile(account_section=section, account_errors=errors,
                           account_values=values, status=status)


def _save_account(section, changes, details=None):
    try:
        for key, value in changes.items():
            setattr(current_user, key, value)
        log_activity(f'profile_{section}_changed', current_user._get_current_object(), details)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Profile account save failed; transaction rolled back')
        return _account_failure(section, {'save': 'Changes were not saved. Please retry.'},
                                {key: str(value or '') for key, value in changes.items()})
    flash(f'{"Name" if section == "name" else "Campus"} updated.', 'success')
    return redirect(url_for('volunteer.profile_page', _anchor=f'change-{section}'), code=303)


@volunteer_bp.route('/profile/name', methods=['POST'])
@login_required
@role_required('volunteer')
def change_name():
    name = request.form.get('name', '').strip()
    if not name or len(name) > 100 or not name.isprintable():
        return _account_failure('name', {'name': 'Enter a name of 1–100 characters without control characters.'},
                                {'name': name})
    return _save_account('name', {'name': name})


@volunteer_bp.route('/profile/campus', methods=['POST'])
@login_required
@role_required('volunteer')
def change_campus():
    value = request.form.get('campus_id', '')
    college = request.form.get('college_affiliation', '').strip()
    campus = official_campus(request.form.get('campus_id', type=int))
    errors = {}
    if campus is None:
        errors['campus_id'] = 'Select one of the nine PSU campuses.'
    elif college not in campus_affiliations(campus):
        errors['college_affiliation'] = 'Select a college for the chosen campus.'
    if errors:
        return _account_failure('campus', errors, dict(campus_id=value, college_affiliation=college))
    return _save_account('campus', dict(campus_id=campus.id, college_affiliation=college),
                         dict(campus_from=current_user.campus_id, campus_to=campus.id))


@volunteer_bp.route('/profile/password', methods=['POST'])
@login_required
@role_required('volunteer')
def change_password():
    errors = {}
    try:
        user = User.query.filter_by(id=current_user.id).populate_existing().with_for_update().one()
        if user.auth_version != session.get('auth_version'):
            db.session.rollback()
            return end_session('Your password changed in another session. Please sign in again.')
        subject = AuthSecurityEvent.subject(f'password_change|{user.id}')
        cutoff = datetime.utcnow() - timedelta(minutes=15)
        # Locking reads see the latest failures even under MySQL repeatable-read isolation.
        attempts = AuthSecurityEvent.query.with_entities(AuthSecurityEvent.id).filter(
            AuthSecurityEvent.action == 'password_change', AuthSecurityEvent.subject_hash == subject,
            AuthSecurityEvent.created_at >= cutoff).limit(5).with_for_update().all()
        if len(attempts) >= 5:
            db.session.rollback()
            return _account_failure('password', {'current_password': 'Too many incorrect attempts. Try again in 15 minutes.'}, status=429)
        current = request.form.get('current_password', '')
        if not user.check_password(current):
            db.session.add(AuthSecurityEvent(action='password_change', subject_hash=subject))
            db.session.commit()
            return _account_failure('password', {'current_password': 'Your current password is incorrect.'})
        password = request.form.get('new_password', '')
        message = password_error(password, password_min_length())
        if message:
            errors['new_password'] = message
        elif user.check_password(password):
            errors['new_password'] = 'Choose a password different from your current password.'
        if password != request.form.get('password_confirmation', ''):
            errors['password_confirmation'] = 'Enter the same new password in both fields.'
        if errors:
            db.session.rollback()
            return _account_failure('password', errors)
        user.set_password(password)
        user.auth_version += 1
        PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
            {'used_at': datetime.utcnow()}, synchronize_session=False)
        log_activity('profile_password_changed', user)
        version = user.auth_version
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Profile password change failed; transaction rolled back')
        return _account_failure('password', {'save': 'Password was not changed. Please retry.'})
    session['auth_version'] = version
    flash('Password changed. Your other sessions have been signed out.', 'success')
    return redirect(url_for('volunteer.profile_page', _anchor='change-password'), code=303)


@volunteer_bp.route('/profile/image/remove', methods=['POST'])
@login_required
@role_required('volunteer')
def remove_profile_image():
    path = current_user.profile_image_path
    current_user.profile_image_path = None
    current_user.profile_image_name = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Profile photo removal failed')
        flash('Photo was not removed. Please retry.', 'error')
        return redirect(url_for('volunteer.profile_page'))
    _delete_profile_image(path)
    flash('Profile image removed.', 'success')
    return redirect(url_for('volunteer.profile_page'))


@volunteer_bp.route('/volunteer_analytics')
@login_required
@role_required('volunteer')
def analytics():
    """Compatibility redirect: volunteers do not receive global analytics."""
    return redirect(url_for('events.volunteer_dash'))
