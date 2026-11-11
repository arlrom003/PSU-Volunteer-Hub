"""Notification model for basic in-app notifications.

Outsiders (ExternalParticipant) do NOT get authenticated notifications because
they have no normal User account. Notifications belong to authenticated PSU
users only.
"""
from datetime import datetime

from app.models import db


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(40), nullable=True)
    related_event_id = db.Column(
        db.Integer, db.ForeignKey('events.id', ondelete='SET NULL'),
        nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship(
        'User',
        backref=db.backref('notifications', lazy='dynamic',
                           cascade='all,delete-orphan'))
    event = db.relationship('Event', backref=db.backref('notifications', lazy=True))

    def __repr__(self):
        return f'<Notification {self.id} user={self.user_id} type={self.notification_type}>'


def notify(user_id, title, message, notification_type=None, related_event_id=None, commit=True):
    """Create a notification row for an authenticated user."""
    note = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_event_id=related_event_id,
    )
    db.session.add(note)
    if commit:
        db.session.commit()
    return note


def notify_campus_coordinators(campus_id, title, message,
                               notification_type=None, related_event_id=None, commit=True):
    """Notify every coordinator assigned to the given campus (conservative
    trigger tied to an existing system action)."""
    from app.models.user import User
    coordinators = db.session.query(User.id).filter_by(
        role='coordinator', campus_id=campus_id).all()
    for coordinator in coordinators:
        notify(coordinator.id, title, message,
               notification_type=notification_type,
               related_event_id=related_event_id, commit=False)
    if commit:
        db.session.commit()
