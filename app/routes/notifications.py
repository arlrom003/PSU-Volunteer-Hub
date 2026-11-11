"""In-app notification routes.

Notifications belong to authenticated PSU users only. A user may read/update
only their own notifications. Cross-user access is denied.
"""
import json
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, abort)
from flask_login import login_required, current_user

from app.models.notification import Notification
from app.models import db
from sqlalchemy.orm import joinedload
from app.reports import parse_date_range, ReportError

notifications_bp = Blueprint('notifications', __name__)


def guidance_content(note):
    """Decode only our guidance format and generate an authorized internal link."""
    if note.notification_type != 'campus_guidance':
        return dict(text=note.message, url=None)
    unavailable = dict(text='This guidance message is unavailable. Review your campus records for current guidance.', url=None)
    try:
        payload = json.loads(note.message)
        identity = payload['identity']
        if (payload['version'] != 1 or not isinstance(payload['text'], str)
                or current_user.role != 'coordinator' or identity['campus_id'] != current_user.campus_id
                or not isinstance(identity['goal_year'], int) or not 1900 <= identity['goal_year'] <= 2100):
            return unavailable
        code = identity['rule']
        if code in ('remaining_goals', 'no_targets'):
            link = (url_for('goals.workspace') if code == 'no_targets' else
                    url_for('goals.details', year=identity['goal_year'], campus=current_user.campus_id))
        elif code in ('pending_attendance', 'missed_targets', 'low_attendance', 'no_activities'):
            scope = identity['scope']
            if not isinstance(scope, dict) or any(not isinstance(value, list) or
                not all(isinstance(item, str) for item in value) for value in scope.values()):
                return unavailable
            query = {key: scope[key][0] for key in ('start_date', 'end_date', 'category', 'activity_name')
                     if scope.get(key)}
            parse_date_range(query.get('start_date'), query.get('end_date'))
            if identity.get('event_id'):
                if not note.event or note.event.campus_id != current_user.campus_id or note.event.id != identity['event_id']:
                    return unavailable
                query['event_id'] = note.event.id
            query['attention'] = code if code != 'no_activities' else ''
            link = url_for('coordinator.analytics', **query) + '#decision-records'
        else:
            return unavailable
        return dict(text=payload['text'], url=link)
    except (ValueError, KeyError, TypeError, AttributeError, ReportError):
        return unavailable


@notifications_bp.route('/notifications')
@login_required
def list_notifications():
    from app.pagination import paginate
    from app.performance import request_value
    pagination = paginate(Notification.query
             .options(joinedload(Notification.event))
             .filter_by(user_id=current_user.id)
             .order_by(Notification.created_at.desc(), Notification.id.desc()))
    notes = pagination.items
    unread = request_value(('unread', current_user.id), lambda: Notification.query.filter_by(
        user_id=current_user.id, is_read=False).count())
    return render_template('notifications/list.html',
                           notifications=notes, unread=unread, pagination=pagination,
                           guidance_content={note.id: guidance_content(note) for note in notes})


@notifications_bp.route('/notifications/<int:notification_id>/read',
                        methods=['POST'])
@login_required
def mark_read(notification_id):
    note = db.session.get(Notification, notification_id)
    if note is None:
        abort(404)
    if note.user_id != current_user.id:
        flash('You cannot modify that notification.', 'error')
        return redirect(url_for('notifications.list_notifications'))
    note.is_read = True
    db.session.commit()
    return redirect(url_for('notifications.list_notifications'))


@notifications_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    (Notification.query
     .filter_by(user_id=current_user.id, is_read=False)
     .update({'is_read': True}))
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notifications.list_notifications'))
