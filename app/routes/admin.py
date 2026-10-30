"""
Admin Routes for PSU Volunteer Hub
====================================
Manages user administration and system management.
"""
import csv
import io
import json
import os
import zipfile
from datetime import date, datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, Response, current_app, session)
from flask_login import login_required, current_user, logout_user
from sqlalchemy.orm import joinedload
from app.models import db
from app.models.user import User, SystemSetting, VolunteerProfile, PasswordResetToken
from app.models.event import ActivityCategory, Campus, Event
from app.models.notification import Notification, notify_campus_coordinators
from app.utils.decorators import role_required
from app.models.audit import AuditLog
from app.models.policy import TermsRevision, PrivacyRevision, ParticipationAgreementRevision
from app.utils.audit import log_activity

admin_bp = Blueprint('admin', __name__, url_prefix='')


def _setting_int(key, default, minimum=1):
    setting = SystemSetting.query.filter_by(key=key).first()
    try:
        return max(minimum, int(setting.value)) if setting else default
    except (TypeError, ValueError):
        return default


def _active_admin_count():
    return User.query.filter_by(role='admin', _is_active=True).count()


def _sync_volunteer_profile(user, old_role=None):
    if user.role == 'volunteer' and user.profile is None:
        db.session.add(VolunteerProfile(user_id=user.id))
    elif old_role == 'volunteer' and user.role != 'volunteer' and user.profile:
        db.session.delete(user.profile)


def _admin_redirect(tab='users'):
    return redirect(url_for('admin.admin_dash', tab=tab))


def _reactivate(user):
    user.is_active = True
    user.deactivated_at = None
    user.reactivation_requested_at = None


@admin_bp.route('/admin_dash')
@login_required
@role_required('admin')
def admin_dash():
    active_tab = request.args.get('tab', 'users')
    if active_tab not in ('users', 'deactivated', 'audit'):
        active_tab = 'users'
    campus_id = request.args.get('campus_id', type=int)
    query = User.query.options(joinedload(User.campus))
    if campus_id:
        query = query.filter(User.campus_id == campus_id)
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    users, deactivated_users, audit_logs = [], [], []
    deactivated_total = User.query.filter(User._is_active.is_(False)).count()
    if active_tab == 'users':
        page_query = query.filter(User._is_active.is_(True)).order_by(User.created_at.desc(), User.id.desc())
    elif active_tab == 'deactivated':
        page_query = query.filter(User._is_active.is_(False)).order_by(User.deactivated_at.asc(), User.id.asc())
    else:
        page_query = AuditLog.query.options(joinedload(AuditLog.actor)).order_by(
            AuditLog.created_at.desc(), AuditLog.id.desc())
    pagination = page_query.paginate(page=page, per_page=25, error_out=False)
    if page > max(pagination.pages, 1):
        return redirect(url_for('admin.admin_dash', tab=active_tab, campus_id=campus_id,
                                page=max(pagination.pages, 1)))
    if active_tab == 'users':
        users = pagination.items
    elif active_tab == 'deactivated':
        deactivated_users = pagination.items
    else:
        audit_logs = pagination.items
    now = datetime.utcnow()
    for user in deactivated_users:
        deactivated_at = user.deactivated_at or user.created_at
        user.deletion_days_left = max(0, 30 - (now - deactivated_at).days)
        user.deletion_expired = now >= deactivated_at + timedelta(days=30)
    active_users = User.query.filter_by(_is_active=True).count()
    pending_approvals = User.query.filter_by(
        role='volunteer', _is_active=True).count()
    try:
        db.session.execute(db.text('SELECT 1'))
        database_status = 'Connected'
    except Exception:
        database_status = 'Unavailable'
    server_status = {'database': database_status}
    campuses = Campus.query.all()
    categories = ActivityCategory.query.order_by(ActivityCategory.name).all()
    return render_template('admin/Admin_mngmt_dash.html',
                           users=users,
                           server_status=server_status,
                           active_users=active_users,
                           pending_approvals=pending_approvals,
                           audit_logs=audit_logs,
                           selected_campus=campus_id,
                           campuses=campuses,
                           categories=categories,
                           deactivated_users=deactivated_users,
                           deactivated_total=deactivated_total,
                           pagination=pagination,
                           active_tab=active_tab)


@admin_bp.route('/admin/users/deactivate/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def deactivate_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if (user.role == 'admin' and user.is_active
            and _active_admin_count() <= 1):
        flash('The final active Admin cannot be deactivated.', 'error')
        return _admin_redirect()
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return _admin_redirect()
    if not user.is_active:
        flash('This account is already deactivated.', 'warning')
        return _admin_redirect('deactivated')
    user.is_active = False
    user.deactivated_at = datetime.utcnow()
    user.reactivation_requested_at = None
    log_activity('user_deactivated', user, {'name': user.name})
    db.session.commit()
    flash(f'User {user.name} has been deactivated.', 'success')
    return _admin_redirect()


@admin_bp.route('/admin/users/<int:user_id>/reactivate', methods=['POST'])
@login_required
@role_required('admin')
def reactivate_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    _reactivate(user)
    log_activity('user_reactivated', user, {'name': user.name})
    db.session.commit()
    flash(f'User {user.name} has been reactivated.', 'success')
    return _admin_redirect('deactivated')


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_expired_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return _admin_redirect('deactivated')
    deadline = (user.deactivated_at or user.created_at) + timedelta(days=30)
    if user.is_active or datetime.utcnow() < deadline:
        abort(403)
    profile_image = user.profile_image_path
    log_activity('user_deleted', user, {'name': user.name})
    db.session.delete(user)
    db.session.commit()
    if profile_image:
        image_path = os.path.join(current_app.static_folder, profile_image)
        if os.path.isfile(image_path):
            os.remove(image_path)
    flash(f'User {user.name} was permanently deleted.', 'success')
    return _admin_redirect('deactivated')


@admin_bp.route('/admin/categories/create', methods=['POST'])
@login_required
@role_required('admin')
def create_category():
    name = ' '.join(request.form.get('name', '').split())
    if not name:
        flash('Category name is required.', 'error')
    elif len(name) > 50:
        flash('Category names must be 50 characters or fewer.', 'error')
    elif ActivityCategory.query.filter(
            db.func.lower(ActivityCategory.name) == name.lower()).first():
        flash('That category already exists.', 'error')
    else:
        category = ActivityCategory(name=name)
        db.session.add(category)
        db.session.flush()
        log_activity('category_created', category, {'name': name})
        db.session.commit()
        flash(f'{name} category created.', 'success')
    return _admin_redirect()


@admin_bp.route('/admin/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_category(category_id):
    category = db.session.get(ActivityCategory, category_id)
    if category is None:
        abort(404)
    if category.name == 'General':
        flash('The General category cannot be removed.', 'error')
        return _admin_redirect()
    events = Event.query.filter_by(category=category.name).all()
    for event in events:
        event.category = 'General'
        title = f'Category changed: {event.title}'
        message = (f'The {category.name} category was removed. Your activity '
                   'was changed to General; please choose a new category.')
        if event.created_by_id:
            db.session.add(Notification(
                user_id=event.created_by_id, title=title, message=message,
                notification_type='category_changed', related_event_id=event.id))
        else:
            coordinators = User.query.filter_by(
                role='coordinator', campus_id=event.campus_id,
                _is_active=True).all()
            for coordinator in coordinators:
                db.session.add(Notification(
                    user_id=coordinator.id, title=title, message=message,
                    notification_type='category_changed', related_event_id=event.id))
    db.session.delete(category)
    log_activity('category_deleted', category,
                 {'name': category.name, 'events_reassigned': len(events)})
    db.session.commit()
    flash(f'{category.name} removed; {len(events)} activities moved to General.',
          'success')
    return _admin_redirect()


@admin_bp.route('/admin/users/role/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def change_role(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    new_role = request.form.get('role', '').strip()
    valid_roles = ['volunteer', 'coordinator', 'director', 'admin']
    if new_role not in valid_roles:
        flash('Invalid role specified.', 'error')
        return redirect(url_for('admin.admin_dash'))
    if (user.role == 'admin' and new_role != 'admin'
            and user.is_active and _active_admin_count() <= 1):
        flash('The final active Admin cannot be demoted.', 'error')
        return redirect(url_for('admin.admin_dash'))
    old_role = user.role
    user.role = new_role
    _sync_volunteer_profile(user, old_role)
    log_activity('user_role_changed', user,
                 {'from': old_role, 'to': new_role})
    db.session.commit()
    flash(f'User {user.name} role changed to {new_role}.', 'success')
    return redirect(url_for('admin.admin_dash'))


@admin_bp.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create_user():
    campuses = Campus.query.all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'volunteer')
        campus_id = request.form.get('campus_id', type=int)
        id_number = request.form.get('id_number', '').strip() or None
        volunteer_type = request.form.get('volunteer_type', '').strip() or None
        college_affiliation = request.form.get(
            'college_affiliation', '').strip() or None
        errors = []
        if not name:
            errors.append('Name is required.')
        if not email:
            errors.append('Email is required.')
        password_min = _setting_int('default_password_length', 8, 8)
        if not password or len(password) < password_min:
            errors.append(
                f'Password must be at least {password_min} characters.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists.')
        if id_number and User.query.filter_by(id_number=id_number).first():
            errors.append('PSU ID already exists.')
        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('admin/admin_user_form.html', user=None,
                                   campuses=campuses,
                                   password_min=password_min)
        user = User(name=name, email=email, role=role, campus_id=campus_id,
                    id_number=id_number, volunteer_type=volunteer_type,
                    college_affiliation=college_affiliation)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == 'volunteer':
            from app.models.user import VolunteerProfile
            db.session.add(VolunteerProfile(user_id=user.id))

        log_activity('user_created', user, {'role': role})
        db.session.commit()
        flash(f'User {name} created successfully.', 'success')
        return redirect(url_for('admin.admin_dash'))
    return render_template('admin/admin_user_form.html', user=None,
                           campuses=campuses,
                           password_min=_setting_int(
                               'default_password_length', 8, 8))


@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    campuses = Campus.query.all()
    if request.method == 'POST':
        user.name = request.form.get('name', user.name).strip()
        user.email = request.form.get('email', user.email).strip()
        submitted_id = request.form.get('id_number', '').strip() or None
        duplicate_id = User.query.filter(
            User.id_number == submitted_id, User.id != user.id).first()
        if submitted_id and duplicate_id:
            flash('PSU ID already exists.', 'error')
            return redirect(url_for('admin.edit_user', user_id=user.id))
        user.id_number = submitted_id
        user.volunteer_type = request.form.get(
            'volunteer_type', '').strip() or None
        user.college_affiliation = request.form.get(
            'college_affiliation', '').strip() or None
        new_role = request.form.get('role', user.role)
        if (user.role == 'admin' and new_role != 'admin'
                and user.is_active and _active_admin_count() <= 1):
            flash('The final active Admin cannot be demoted.', 'error')
            return redirect(url_for('admin.edit_user', user_id=user.id))
        old_role = user.role
        user.role = new_role
        user.campus_id = request.form.get(
            'campus_id', user.campus_id, type=int)
        _sync_volunteer_profile(user, old_role)
        log_activity('user_updated', user,
                     {'role_from': old_role, 'role_to': new_role})
        db.session.commit()
        flash(f'User {user.name} updated.', 'success')
        if user.id == current_user.id and old_role != new_role:
            return redirect(url_for('dashboard'))
        return redirect(url_for('admin.admin_dash'))
    return render_template('admin/admin_user_form.html', user=user,
                           campuses=campuses,
                           password_min=_setting_int(
                               'default_password_length', 8, 8))


@admin_bp.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    new_password = request.form.get('new_password', '')
    password_min = _setting_int('default_password_length', 8, 8)
    if len(new_password) < password_min:
        flash(f'Password must be at least {password_min} characters.', 'error')
        return redirect(url_for('admin.admin_dash'))
    user.set_password(new_password)
    user.auth_version += 1
    PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update(
        {'used_at': datetime.utcnow()})
    log_activity('user_password_reset', user)
    db.session.commit()
    if user.id == current_user.id:
        session.clear()
        logout_user()
        flash('Your password was reset. Sign in again with your new password.', 'success')
        return redirect(url_for('auth.login'))
    flash(f'Password reset for {user.name}.', 'success')
    return redirect(url_for('admin.admin_dash'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def settings():
    if request.method == 'POST':
        allowed = {
            'max_slots_per_event': (1, 10000),
            'default_password_length': (8, 128),
        }
        values = {}
        for key, (minimum, maximum) in allowed.items():
            raw = request.form.get(key)
            if raw is None:
                continue
            raw = raw.strip()
            try:
                value = int(raw)
            except ValueError:
                flash(f'{key.replace("_", " ").title()} must be a number.', 'error')
                return redirect(url_for('admin.settings'))
            if not minimum <= value <= maximum:
                flash(f'{key.replace("_", " ").title()} must be between {minimum} and {maximum}.', 'error')
                return redirect(url_for('admin.settings'))
            values[key] = str(value)
        for key, value in values.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSetting(key=key, value=value)
                db.session.add(setting)
        if values:
            log_activity('settings_updated', SystemSetting(),
                         {'keys': sorted(values)})
        db.session.commit()
        flash('Settings saved.', 'success')
    settings = {s.key: s.value for s in SystemSetting.query.all()}
    return render_template('admin/settings.html', settings=settings)


@admin_bp.route('/admin/campuses/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create_campus():
    if request.method == 'POST':
        name = ' '.join(request.form.get('name', '').split())
        code = request.form.get('code', '').strip().upper()
        description = request.form.get('description', '').strip()
        errors = []
        if not name:
            errors.append('Campus name is required.')
        if not code or not code.replace('-', '').isalnum():
            errors.append('Campus code must contain letters, numbers, or hyphens.')
        if Campus.query.filter(db.func.lower(Campus.name) == name.lower()).first():
            errors.append('Campus name already exists.')
        if Campus.query.filter(db.func.upper(Campus.code) == code).first():
            errors.append('Campus code already exists.')
        if not errors:
            campus = Campus(name=name, code=code, description=description)
            db.session.add(campus)
            db.session.flush()
            log_activity('campus_created', campus, {'name': name, 'code': code})
            db.session.commit()
            flash(f'{name} campus created.', 'success')
            return redirect(url_for('admin.admin_dash'))
        for error in errors:
            flash(error, 'error')
    return render_template('admin/campus_form.html')


def _backup_value(value):
    if value is None:
        return ''
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


USER_IMPORT_COLUMNS = (
    'name', 'email', 'password', 'role', 'campus_code', 'id_number',
    'volunteer_type', 'college_affiliation',
)


def _clean_import_row(row):
    return {key: ' '.join((row.get(key) or '').split())
            for key in USER_IMPORT_COLUMNS}


@admin_bp.route('/admin/users/import-template.csv')
@login_required
@role_required('admin')
def user_import_template():
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=USER_IMPORT_COLUMNS)
    writer.writeheader()
    writer.writerow({
        'name': 'Example Volunteer',
        'email': 'volunteer@example.edu',
        'password': 'ChangeMe123',
        'role': 'volunteer',
        'campus_code': 'LINGAYEN',
        'id_number': '',
        'volunteer_type': 'Student',
        'college_affiliation': '',
    })
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': 'attachment;filename=psu_user_import_template.csv'})


@admin_bp.route('/admin/users/export.csv')
@login_required
@role_required('admin')
def export_users_csv():
    output = io.StringIO(newline='')
    fields = ('name', 'email', 'role', 'campus_code', 'id_number',
              'volunteer_type', 'college_affiliation', 'is_active', 'created_at')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for user in User.query.order_by(User.name).all():
        writer.writerow({
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'campus_code': user.campus.code if user.campus else '',
            'id_number': user.id_number or '',
            'volunteer_type': user.volunteer_type or '',
            'college_affiliation': user.college_affiliation or '',
            'is_active': 'yes' if user.is_active else 'no',
            'created_at': user.created_at.isoformat() if user.created_at else '',
        })
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': 'attachment;filename=psu_users.csv'})


@admin_bp.route('/admin/terms', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_terms():
    if request.method == 'POST':
        title = ' '.join(request.form.get('title', '').split())
        version = request.form.get('version', '').strip()
        body = request.form.get('body', '').strip()
        if not title or not version or not body:
            flash('Title, version, and Terms of Use text are required.', 'error')
        elif TermsRevision.query.filter_by(version=version).first():
            flash('That terms version already exists.', 'error')
        else:
            TermsRevision.query.update({TermsRevision.is_active: False})
            revision = TermsRevision(
                title=title, body=body, version=version,
                published_by_id=current_user.id, is_active=True)
            db.session.add(revision)
            db.session.flush()
            log_activity('terms_published', revision, {'version': version})
            db.session.commit()
            flash(f'Terms version {version} is now active.', 'success')
            return redirect(url_for('admin.manage_terms'))
    revisions = TermsRevision.query.order_by(
        TermsRevision.published_at.desc()).all()
    return render_template('admin/terms_management.html', revisions=revisions)


@admin_bp.route('/admin/policies/<document>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_policy(document):
    documents = {
        'privacy': (PrivacyRevision, 'Privacy Notice'),
        'participation-agreement': (ParticipationAgreementRevision, 'Default Participation Agreement'),
    }
    if document not in documents:
        abort(404)
    model, label = documents[document]
    if request.method == 'POST':
        title, version, body = (' '.join(request.form.get('title', '').split()),
                                request.form.get('version', '').strip(),
                                request.form.get('body', '').strip())
        if not title or not version or not body:
            flash('Title, version, and document text are required.', 'error')
        elif model.query.filter_by(version=version).first():
            flash('That version already exists.', 'error')
        else:
            model.query.update({model.is_active: False})
            revision = model(title=title, version=version, body=body,
                             is_active=True, published_by_id=current_user.id)
            db.session.add(revision)
            db.session.flush()
            log_activity(f'{document}_published', revision, {'version': version})
            db.session.commit()
            flash(f'{label} version {version} is now active.', 'success')
            return redirect(url_for('admin.manage_policy', document=document))
    return render_template('admin/policy_management.html', label=label,
                           revisions=model.query.order_by(model.published_at.desc()).all())


@admin_bp.route('/admin/users/import', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def import_users_csv():
    password_min = _setting_int('default_password_length', 8, 8)
    if request.method == 'GET':
        return render_template('admin/user_import.html', password_min=password_min)

    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Choose a CSV file to import.', 'error')
        return redirect(url_for('admin.import_users_csv'))
    if not upload.filename.lower().endswith('.csv'):
        flash('The import file must be a CSV.', 'error')
        return redirect(url_for('admin.import_users_csv'))
    try:
        stream = io.StringIO(upload.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
    except UnicodeDecodeError:
        flash('The CSV must use UTF-8 text encoding.', 'error')
        return redirect(url_for('admin.import_users_csv'))
    if set(USER_IMPORT_COLUMNS) - set(reader.fieldnames or []):
        flash('The CSV does not match the downloadable import template.', 'error')
        return redirect(url_for('admin.import_users_csv'))

    campuses = {campus.code.upper(): campus for campus in Campus.query.all()}
    existing_emails = {email.casefold() for email, in db.session.query(User.email)}
    existing_ids = {number for number, in db.session.query(User.id_number)
                    if number}
    seen_emails, seen_ids, rows, errors = set(), set(), [], []
    for line_number, raw_row in enumerate(reader, start=2):
        row = _clean_import_row(raw_row)
        email = row['email'].casefold()
        role = row['role'].lower()
        campus = campuses.get(row['campus_code'].upper()) if row['campus_code'] else None
        if not row['name'] or not email or not row['password']:
            errors.append(f'Row {line_number}: name, email, and password are required.')
        elif len(row['password']) < password_min:
            errors.append(f'Row {line_number}: password is too short.')
        elif role not in ('volunteer', 'coordinator', 'director', 'admin'):
            errors.append(f'Row {line_number}: role is invalid.')
        elif row['campus_code'] and campus is None:
            errors.append(f'Row {line_number}: campus code is invalid.')
        elif email in existing_emails or email in seen_emails:
            errors.append(f'Row {line_number}: email already exists.')
        elif row['id_number'] and (row['id_number'] in existing_ids or row['id_number'] in seen_ids):
            errors.append(f'Row {line_number}: PSU ID already exists.')
        else:
            row['email'] = email
            row['role'] = role
            row['campus_id'] = campus.id if campus else None
            rows.append(row)
            seen_emails.add(email)
            if row['id_number']:
                seen_ids.add(row['id_number'])
    if errors:
        for error in errors[:10]:
            flash(error, 'error')
        if len(errors) > 10:
            flash(f'{len(errors) - 10} additional rows have errors.', 'error')
        return redirect(url_for('admin.import_users_csv'))
    if not rows:
        flash('The CSV contains no user rows.', 'warning')
        return redirect(url_for('admin.import_users_csv'))

    for row in rows:
        user = User(
            name=row['name'], email=row['email'], role=row['role'],
            campus_id=row['campus_id'], id_number=row['id_number'] or None,
            volunteer_type=row['volunteer_type'] or None,
            college_affiliation=row['college_affiliation'] or None,
        )
        user.set_password(row['password'])
        db.session.add(user)
        db.session.flush()
        if user.role == 'volunteer':
            db.session.add(VolunteerProfile(user_id=user.id))
        log_activity('user_imported', user, {'role': user.role})
    db.session.commit()
    flash(f'{len(rows)} user account(s) imported.', 'success')
    return redirect(url_for('admin.admin_dash'))


@admin_bp.route('/admin/backup')
@login_required
@role_required('admin')
def backup():
    """Download a portable, credential-free application data archive."""
    archive_buffer = io.BytesIO()
    manifest = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'database_dialect': db.engine.dialect.name,
        'tables': [],
    }
    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for table in db.metadata.sorted_tables:
            columns = [column for column in table.columns
                       if column.name != 'password_hash']
            rows = db.session.execute(
                db.select(*columns).select_from(table)).all()
            text_buffer = io.StringIO(newline='')
            writer = csv.writer(text_buffer)
            writer.writerow([column.name for column in columns])
            for row in rows:
                writer.writerow([_backup_value(value) for value in row])
            archive.writestr(f'tables/{table.name}.csv',
                             text_buffer.getvalue().encode('utf-8-sig'))
            manifest['tables'].append({
                'name': table.name,
                'columns': [column.name for column in columns],
                'row_count': len(rows),
            })
        archive.writestr('manifest.json', json.dumps(
            manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    archive_buffer.seek(0)
    filename = f'psu-volunteer-hub-backup-{datetime.now():%Y%m%d-%H%M%S}.zip'
    return Response(archive_buffer.getvalue(), mimetype='application/zip',
                    headers={'Content-Disposition':
                             f'attachment; filename={filename}'})
