"""
Volunteer Profile Routes for PSU Volunteer Hub
===============================================
Handles profile viewing/editing, participation history, and
profile-level analytics (impact stats, badges, level progress,
preferred categories, and event recommendations).
"""
from collections import Counter
import os
import uuid
from pathlib import Path

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_required, current_user
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from app.models import db
from app.models.user import VolunteerProfile, Skill, Interest
from app.models.event import Registration, Event, Attendance
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from app.recommendation.engine import get_recommendations
from app.utils.decorators import role_required

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
    profile = VolunteerProfile.query.filter_by(user_id=current_user.id).first()
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
                profile = VolunteerProfile.query.filter_by(user_id=current_user.id).first()
                current_app.logger.exception('Profile save failed')
                errors['save'] = 'Profile was not saved. Please retry. If you chose a photo, choose it again.'
            else:
                if image_path:
                    _delete_profile_image(old_path)
                flash('Profile updated successfully!', 'success')
                return redirect(url_for('volunteer.profile_page'))

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
        errors=errors,
        selected_skills=selected_skills,
        selected_interests=selected_interests,
        skill_catalog=Skill.query.order_by(Skill.name).all(),
        interest_catalog=Interest.query.order_by(Interest.name).all(),
    ), (422 if errors else 200)


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
