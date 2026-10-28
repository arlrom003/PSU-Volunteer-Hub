"""
Authentication Routes for PSU Volunteer Hub
=============================================
Handles login, registration, and logout.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from datetime import datetime, timedelta
from hashlib import sha256
from urllib.parse import unquote
import secrets
from app.models.user import (User, Interest, Skill, SystemSetting,
                             AuthSecurityEvent, PasswordResetToken)
from app.models.notification import Notification
from app.models.policy import (TermsRevision, TermsAcceptance, PrivacyRevision,
                               PrivacyAcknowledgement)
from app.models import db
from app.services.email import send_email
from app.services.session_idle import session_status
import time

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

VOLUNTEER_TYPES = {'student', 'faculty', 'staff'}
SEXES = {'male', 'female', 'prefer_not_to_say'}
AUTH_LIMITS = {'login': (5, timedelta(minutes=15)),
               'register': (5, timedelta(hours=1)),
               'reactivation': (5, timedelta(minutes=15)),
               'password_reset': (3, timedelta(hours=1))}


def _request_ip():
    return request.remote_addr or 'unknown'


def _throttle_key(action, subject=''):
    return AuthSecurityEvent.subject(f'{action}|{_request_ip()}|{subject.lower()}')


def _is_limited(action, subject=''):
    limit, window = AUTH_LIMITS[action]
    cutoff = datetime.utcnow() - window
    return AuthSecurityEvent.query.filter(
        AuthSecurityEvent.action == action,
        AuthSecurityEvent.subject_hash == _throttle_key(action, subject),
        AuthSecurityEvent.created_at >= cutoff).count() >= limit


def _record_attempt(action, subject=''):
    db.session.add(AuthSecurityEvent(
        action=action, subject_hash=_throttle_key(action, subject)))
    db.session.commit()


def _too_many_attempts():
    return render_template(
        'login.html', form_error='Too many attempts. Please wait and try again.'), 429


def _password_min_length():
    setting = SystemSetting.query.filter_by(
        key='default_password_length').first()
    try:
        return max(8, int(setting.value)) if setting else 8
    except (TypeError, ValueError):
        return 8


def _active_terms():
    return TermsRevision.query.filter_by(is_active=True).order_by(
        TermsRevision.published_at.desc()).first()


def _active_privacy():
    return PrivacyRevision.query.filter_by(is_active=True).order_by(
        PrivacyRevision.published_at.desc()).first()


def _dashboard_endpoint(user):
    return {
        'volunteer': 'events.volunteer_dash',
        'coordinator': 'coordinator.coordinator_dash',
        'director': 'director.director_dash',
        'admin': 'admin.admin_dash',
    }.get(user.role, 'dashboard')


def _safe_next_url(target):
    """Allow only root-relative paths; reject encoded external URL variants."""
    if isinstance(target, str) and target.startswith('/'):
        decoded = unquote(target)
        if (decoded.startswith('/') and not decoded.startswith('//')
                and '\\' not in decoded
                and not any(ord(char) < 32 or ord(char) == 127 for char in decoded)):
            return target
    return url_for(_dashboard_endpoint(current_user))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login form submission and display login page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')

        if _is_limited('login', identifier):
            return _too_many_attempts()

        if not identifier or not password:
            return render_template(
                'login.html', form_error='Please enter both email/ID and password.')

        # Institutional email matching is case-insensitive; PSU IDs are exact.
        user = User.query.filter(or_(
            db.func.lower(User.email) == identifier.lower(),
            User.id_number == identifier,
        )).first()

        permanent_password = user is not None and user.check_password(password)
        recovery = None
        if user is not None and not permanent_password and user.is_active:
            recovery = PasswordResetToken.query.filter_by(
                user_id=user.id, token_hash=sha256(password.encode()).hexdigest(),
                used_at=None).filter(PasswordResetToken.expires_at > datetime.utcnow()).first()

        if not permanent_password and recovery is None:
            _record_attempt('login', identifier)
            return render_template(
                'login.html', form_error='Invalid email/ID or password.')

        if not user.is_active:
            session['reactivation_user_id'] = user.id
            return render_template('login.html', show_reactivation_modal=True)

        if recovery is not None:
            session.clear()
            session['password_reset_hash'] = recovery.token_hash
            return redirect(url_for('auth.reset_password'))

        session.pop('password_reset_hash', None)
        login_user(user, remember=False)
        session['auth_version'] = user.auth_version
        session['last_activity_at'] = time.time()

        next_page = _safe_next_url(request.args.get('next'))
        active_terms = _active_terms()
        if active_terms and not TermsAcceptance.query.filter_by(
                user_id=user.id, revision_id=active_terms.id).first():
            session['terms_next'] = next_page
            return redirect(url_for('auth.accept_terms'))
        return redirect(next_page)

    return render_template('login.html')


@auth_bp.route('/session', methods=['GET', 'POST'])
def session_activity():
    """Read the deadline without renewal; CSRF-protected POST records activity."""
    from flask import jsonify
    if not current_user.is_authenticated:
        response = jsonify(sign_in_url=url_for('auth.login'))
        response.status_code = 401
    else:
        from flask_wtf.csrf import generate_csrf
        response = jsonify(**session_status(), csrf_token=generate_csrf())
    response.headers['Cache-Control'] = 'no-store'
    return response


@auth_bp.route('/request-reactivation', methods=['POST'])
def request_reactivation():
    """Create one admin-visible appeal after a valid deactivated login."""
    user_id = session.get('reactivation_user_id')
    if _is_limited('reactivation', str(user_id or '')):
        return _too_many_attempts()
    user = db.session.get(User, user_id) if user_id else None
    if user is None or user.is_active:
        flash('Please sign in again before requesting reactivation.', 'error')
        return redirect(url_for('auth.login'))
    if user.reactivation_requested_at:
        flash('Your reactivation request is already pending review.', 'warning')
        return redirect(url_for('auth.login'))

    user.reactivation_requested_at = datetime.utcnow()
    db.session.add(AuthSecurityEvent(
        action='reactivation', subject_hash=_throttle_key('reactivation', str(user_id))))
    administrators = User.query.filter_by(role='admin', _is_active=True).all()
    for administrator in administrators:
        db.session.add(Notification(
            user_id=administrator.id,
            title=f'Reactivation request: {user.name}',
            message=(f'{user.name} ({user.email}) requested reactivation of '
                     'their deactivated account.'),
            notification_type='reactivation_request'))
    db.session.commit()
    session.pop('reactivation_user_id', None)
    flash('Your reactivation request has been sent to an administrator.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/interests', methods=['GET', 'POST'])
def interests():
    """Onboarding step 1: pick interests; connected skills reveal inline."""
    from config import Config
    interest_skill_map = getattr(Config, 'INTEREST_SKILL_MAP', {})
    errors = {}
    selections_required = bool(Interest.query.first() and Skill.query.first())

    if request.method == 'POST':
        selected_interests = Interest.query.filter(
            Interest.id.in_(request.form.getlist('interests')),
            Interest.name.in_(interest_skill_map),
        ).all()
        selected_interest_ids = [str(interest.id) for interest in selected_interests]
        allowed_skill_names = {
            skill_name
            for interest in selected_interests
            for skill_name in interest_skill_map.get(interest.name, [])
        }
        allowed_skill_ids = {
            str(skill.id)
            for skill in Skill.query.filter(Skill.name.in_(allowed_skill_names)).all()
        }
        session['selected_interests'] = selected_interest_ids
        session['selected_skills'] = [
            skill_id for skill_id in request.form.getlist('skills')
            if skill_id in allowed_skill_ids
        ]
        # Match final registration's existing catalogue-dependent requirements.
        if selections_required:
            if not selected_interest_ids:
                errors['interests'] = 'Select at least one interest.'
            if not session['selected_skills']:
                errors['skills'] = 'Select at least one skill.'
        if not errors:
            return redirect(url_for('auth.register'))

    configured_names = list(interest_skill_map)
    all_interests = Interest.query.filter(
        Interest.name.in_(configured_names)
    ).order_by(Interest.name).all()
    interests_data = []
    for interest in all_interests:
        skill_names = interest_skill_map.get(interest.name, [])
        connected = (
            Skill.query.filter(Skill.name.in_(skill_names)).all()
            if skill_names else []
        )
        interests_data.append({'interest': interest, 'skills': connected})

    return render_template(
        'interests.html', interests_data=interests_data, errors=errors,
        selections_required=selections_required,
        selected_interests=session.get('selected_interests', []),
        selected_skills=session.get('selected_skills', []))


@auth_bp.route('/skills', methods=['GET', 'POST'])
def skills():
    """Compatibility endpoint for the former separate skills step."""
    return redirect(url_for('auth.interests'))


@auth_bp.route('/complete-sex', methods=['GET', 'POST'])
@login_required
def complete_sex():
    """Collect the required demographic field from pre-existing volunteers."""
    if current_user.role != 'volunteer' or current_user.sex:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        sex = request.form.get('sex', '').strip().lower()
        if sex not in SEXES:
            flash('Select a sex response to continue.', 'error')
        else:
            current_user.sex = sex
            db.session.commit()
            flash('Profile information updated.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('auth/complete_sex.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle new user registration."""
    from app.models.event import Campus
    if current_user.is_authenticated:
        # Allow starting a new registration even when a session is active
        # (e.g. an admin/director testing the signup flow): sign out first
        # instead of bouncing the visitor to their own dashboard.
        logout_user()

    campuses = Campus.query.order_by(db.func.lower(Campus.name), Campus.name, Campus.id).all()
    interests = Interest.query.all()
    skills = Skill.query.all()
    active_terms = _active_terms()
    active_privacy = _active_privacy()

    if request.method == 'POST':
        # 1. Grab inputs from Signup.html
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        full_name = f"{first_name} {last_name}".strip()

        email = request.form.get('email', '').strip().lower()
        if _is_limited('register', email):
            return _too_many_attempts()
        password = request.form.get('password', '')
        password_confirmation = request.form.get('password_confirmation')
        id_number = request.form.get('id_number', '').strip() or None
        volunteer_type = request.form.get('volunteer_type', '').strip().lower()
        sex = request.form.get('sex', '').strip().lower()
        college_affiliation = request.form.get(
            'college_affiliation', '').strip()
        campus_id = request.form.get('campus', type=int)
        password_min = _password_min_length()

        # Validation
        errors = {}
        if not first_name:
            errors['first_name'] = 'First name is required.'
        if not last_name:
            errors['last_name'] = 'Last name is required.'
        if not email:
            errors['email'] = 'Email is required.'
        if not password:
            errors['password'] = 'Password is required.'
        elif len(password) < password_min:
            errors['password'] = f'Password must be at least {password_min} characters.'
        if (password_confirmation is not None
                and password != password_confirmation):
            errors['password_confirmation'] = 'Password confirmation does not match.'

        if not id_number:
            errors['id_number'] = 'PSU ID Number is required for volunteers.'
        if volunteer_type not in VOLUNTEER_TYPES:
            errors['volunteer_type'] = 'Select Student, Faculty, or Staff.'
        if sex not in SEXES:
            errors['sex'] = 'Select a sex response.'
        if not college_affiliation:
            errors['college_affiliation'] = 'College affiliation is required.'
        if active_terms and request.form.get('terms_accepted') != 'on':
            errors['terms_accepted'] = 'You must accept the current Terms of Use.'
        if active_privacy and request.form.get('privacy_acknowledged') != 'on':
            errors['privacy_acknowledged'] = 'You must acknowledge the current Privacy Notice.'

        # Check duplicate email
        if email and User.query.filter(
                db.func.lower(User.email) == email).first():
            errors['email'] = 'An account with this email already exists.'
        if id_number and User.query.filter_by(id_number=id_number).first():
            errors['id_number'] = 'An account with this PSU ID already exists.'

        # Resolve campus string to Campus Model DB record
        campus_obj = db.session.get(Campus, campus_id) if campus_id else None
        if campus_obj is None:
            errors['campus'] = 'Select a valid PSU campus.'

        selected_interest_ids = request.form.getlist('interests') or session.get(
            'selected_interests', [])
        selected_skill_ids = request.form.getlist('skills') or session.get(
            'selected_skills', [])
        if interests and skills:
            if not selected_interest_ids:
                errors['interests'] = 'Select at least one interest.'
            if not selected_skill_ids:
                errors['skills'] = 'Select at least one skill.'

        if errors:
            _record_attempt('register', email)
            return render_template('Signup.html', campuses=campuses,
                                   interests=interests, skills=skills,
                                   password_min=password_min,
                                   active_terms=active_terms, active_privacy=active_privacy,
                                   errors=errors)

        # Public registration always creates a volunteer. Privileged roles
        # can only be assigned through the protected Admin interface.
        assigned_role = 'volunteer'

        # 3. Create User record
        user = User(
            name=full_name,
            email=email,
            id_number=id_number,
            role=assigned_role,
            volunteer_type=volunteer_type,
            sex=sex,
            college_affiliation=college_affiliation,
            campus_id=campus_obj.id if campus_obj else None
        )
        user.set_password(password)
        db.session.add(user)

        # 4. Attach Interest records carried over from the onboarding wizard
        #    (steps 1 & 2 stored them in the session).
        if selected_interest_ids:
            interest_ids = [
                int(i_id) for i_id in selected_interest_ids if str(i_id).isdigit()]
            chosen_interests = Interest.query.filter(
                Interest.id.in_(interest_ids)).all()

            # Populates user_interests pivot table automatically
            user.interests.extend(chosen_interests)

        # 4b. Attach Skill records carried over from the onboarding wizard
        if selected_skill_ids:
            skill_ids = [
                int(s_id) for s_id in selected_skill_ids if str(s_id).isdigit()]
            chosen_skills = Skill.query.filter(
                Skill.id.in_(skill_ids)).all()
            user.skills.extend(chosen_skills)

        # 5. Commit to MySQL
        db.session.flush()

        # Create a VolunteerProfile for volunteers so the recommendation
        # engine can cold-start instead of showing nothing.
        if assigned_role == 'volunteer':
            from app.models.user import VolunteerProfile
            db.session.add(VolunteerProfile(user_id=user.id))
        if active_terms:
            db.session.add(TermsAcceptance(
                user_id=user.id, revision_id=active_terms.id))
        if active_privacy:
            db.session.add(PrivacyAcknowledgement(
                user_id=user.id, revision_id=active_privacy.id))

        db.session.commit()

        # Clear session keys after successful registration
        session.pop('selected_interests', None)
        session.pop('selected_skills', None)

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('Signup.html', campuses=campuses,
                           interests=interests, skills=skills,
                           password_min=_password_min_length(),
                           active_terms=active_terms, active_privacy=active_privacy)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Email a short-lived recovery password without changing the current one."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email or len(email) > 120 or email.count('@') != 1 or any(c.isspace() for c in email):
            return render_template('auth/forgot_password.html', errors={
                'email': 'Enter the email address registered to your account.'}), 400
        if _is_limited('password_reset', email):
            flash('If an active account uses that email, a temporary password will arrive shortly. Check your spam folder too.', 'info')
            return redirect(url_for('auth.login'))
        _record_attempt('password_reset', email)
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.is_active:
            raw_token = secrets.token_urlsafe(15)
            PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
                {'used_at': datetime.utcnow()})
            db.session.add(PasswordResetToken(
                user_id=user.id, token_hash=sha256(raw_token.encode()).hexdigest(),
                expires_at=datetime.utcnow() + timedelta(minutes=30)))
            try:
                send_email(user.email, 'Your PSU Volunteer Hub temporary password',
                           f'Temporary password: {raw_token}\n\n'
                           'Open PSU Volunteer Hub and sign in with your registered email '
                           'and this temporary password within 30 minutes. You must choose '
                           'a new password before accessing your account.\n\n'
                           'Only the latest temporary password works. It can complete one reset.\n'
                           'If you did not request this, ignore this email. '
                           'Your current password has not changed.')
            except OSError:
                db.session.rollback()
                current_app.logger.error('Password reset email delivery failed; check email provider configuration')
            else:
                db.session.commit()
        flash('If an active account uses that email, a temporary password will arrive shortly. Check your spam folder too.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', errors={})


@auth_bp.route('/reset-password', defaults={'token': None}, methods=['GET', 'POST'])
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    token_hash = sha256(token.encode()).hexdigest() if token else session.get('password_reset_hash')
    record = PasswordResetToken.query.filter_by(token_hash=token_hash, used_at=None).first()
    if record is None or record.expires_at <= datetime.utcnow() or not record.user.is_active:
        session.pop('password_reset_hash', None)
        flash('This password reset is invalid or has expired. Request another temporary password.', 'error')
        return redirect(url_for('auth.forgot_password'))
    errors = {}
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirmation = request.form.get('password_confirmation', '')
        minimum = _password_min_length()
        if len(password) < minimum:
            errors['password'] = f'Use at least {minimum} characters.'
        if password != confirmation:
            errors['password_confirmation'] = 'Enter the same new password in both fields.'
        if sha256(password.encode()).hexdigest() == record.token_hash:
            errors['password'] = 'Choose a new password different from your temporary password.'
        if not errors:
            claimed = PasswordResetToken.query.filter_by(id=record.id, used_at=None).filter(
                PasswordResetToken.expires_at > datetime.utcnow()).update(
                    {'used_at': datetime.utcnow()}, synchronize_session=False)
            if not claimed:
                db.session.rollback()
                session.pop('password_reset_hash', None)
                flash('This password reset has expired or was already used. Request another temporary password.', 'error')
                return redirect(url_for('auth.forgot_password'))
            record.user.set_password(password)
            record.user.auth_version += 1
            PasswordResetToken.query.filter_by(user_id=record.user_id, used_at=None).update(
                {'used_at': datetime.utcnow()}, synchronize_session=False)
            db.session.commit()
            session.pop('password_reset_hash', None)
            flash('Password reset. Please sign in.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', password_min=_password_min_length(), errors=errors)


@auth_bp.route('/privacy', methods=['GET', 'POST'])
@login_required
def accept_privacy():
    revision = _active_privacy()
    if revision is None:
        return redirect(_safe_next_url(session.pop('privacy_next', None)))
    accepted = PrivacyAcknowledgement.query.filter_by(
        user_id=current_user.id, revision_id=revision.id).first()
    if accepted:
        return redirect(_safe_next_url(session.pop('privacy_next', None)))
    if request.method == 'POST' and request.form.get('acknowledge_privacy') == 'on':
        db.session.add(PrivacyAcknowledgement(user_id=current_user.id, revision_id=revision.id))
        db.session.commit()
        flash('Privacy Notice acknowledged.', 'success')
        return redirect(_safe_next_url(session.pop('privacy_next', None)))
    if request.method == 'POST':
        flash('You must acknowledge the Privacy Notice to continue.', 'error')
    return render_template('auth/privacy_acceptance.html', revision=revision)


@auth_bp.route('/terms', methods=['GET', 'POST'])
@login_required
def accept_terms():
    """Require acceptance of the current published terms before proceeding."""
    revision = _active_terms()
    if revision is None:
        return redirect(_safe_next_url(session.pop('terms_next', None)))
    accepted = TermsAcceptance.query.filter_by(
        user_id=current_user.id, revision_id=revision.id).first()
    if accepted:
        return redirect(_safe_next_url(session.pop('terms_next', None)))
    if request.method == 'POST':
        if request.form.get('accept_terms') != 'on':
            flash('You must accept the Terms of Use to continue.', 'error')
        else:
            db.session.add(TermsAcceptance(
                user_id=current_user.id, revision_id=revision.id))
            db.session.commit()
            flash('Terms of Use accepted.', 'success')
            return redirect(_safe_next_url(session.pop('terms_next', None)))
    return render_template('auth/terms_acceptance.html', revision=revision)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
