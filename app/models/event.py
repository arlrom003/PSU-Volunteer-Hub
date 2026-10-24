"""
Event Management Models for PSU Volunteer Hub
==============================================
Models for activities/events, registrations, attendance tracking,
milestones, campuses, recommendation logs, and analytics summaries.
"""
from datetime import datetime
from app.models import db
from app.models.user import Skill

# Junction table for event required skills (3NF)
event_skills = db.Table(
    'event_skills',
    db.Column('event_id', db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), primary_key=True),
    db.Column('skill_id', db.Integer, db.ForeignKey(
        'skills.id', ondelete='CASCADE'), primary_key=True)
)

event_sdgs = db.Table(
    'event_sdgs',
    db.Column('event_id', db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), primary_key=True),
    db.Column('sdg_id', db.Integer, db.ForeignKey(
        'sdg_goals.id', ondelete='RESTRICT'), primary_key=True),
)


class SdgGoal(db.Model):
    """Official Sustainable Development Goals available for activities."""
    __tablename__ = 'sdg_goals'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)


class Event(db.Model):
    """
    Represents a volunteer activity/event posted by coordinators.
    """
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    cancellation_deadline = db.Column(db.DateTime, nullable=True)
    category = db.Column(db.String(50), default='General')
    location = db.Column(db.String(500), default='')
    slots = db.Column(db.Integer, default=0)
    target_participants = db.Column(db.Integer, nullable=True)
    participation_agreement_text = db.Column(db.Text, nullable=True)
    participation_agreement_version = db.Column(db.String(30), nullable=True)
    nda_required = db.Column(db.Boolean, default=False, nullable=False)
    nda_text = db.Column(db.Text, nullable=True)
    nda_version = db.Column(db.String(30), nullable=True)
    cover_image_path = db.Column(db.String(255), nullable=True)
    cover_image_name = db.Column(db.String(255), nullable=True)
    cover_uploaded_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    cover_uploaded_at = db.Column(db.DateTime, nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey(
        'campuses.id', ondelete='SET NULL'))
    created_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True)

    # Relationships
    campus = db.relationship('Campus', backref='events', lazy=True)
    created_by = db.relationship(
        'User', foreign_keys=[created_by_id],
        backref=db.backref('created_events', lazy=True))
    cover_uploaded_by = db.relationship(
        'User', foreign_keys=[cover_uploaded_by_id],
        backref=db.backref('uploaded_event_covers', lazy=True))
    registrations = db.relationship(
        'Registration', backref='event', lazy=True, cascade='all, delete-orphan')
    attendance_records = db.relationship(
        'Attendance', backref='event', lazy=True, cascade='all, delete-orphan')
    milestones = db.relationship(
        'Milestone', backref='event', lazy=True, cascade='all, delete-orphan')
    announcements = db.relationship(
        'EventAnnouncement', backref='event', lazy=True,
        cascade='all, delete-orphan')

    # 3NF Skills relationship
    required_skills_rel = db.relationship(
        'Skill', secondary=event_skills, backref=db.backref('events', lazy='dynamic'))
    sdgs = db.relationship(
        'SdgGoal', secondary=event_sdgs,
        backref=db.backref('events', lazy='dynamic'), order_by='SdgGoal.number')

    @property
    def required_skills(self) -> str:
        """Backward-compatible helper string for UI templates."""
        return ", ".join([s.name for s in self.required_skills_rel])

    @required_skills.setter
    def required_skills(self, skills_string: str):
        if not skills_string:
            self.required_skills_rel = []
            return

        # Explicitly ensure this event object is registered in the session
        # before running queries to avoid autoflush warnings.
        if db.session and self not in db.session:
            db.session.add(self)

        from app.models.user import Skill
        names = [s.strip() for s in skills_string.split(',') if s.strip()]

        skills_objects = []
        for name in names:
            skill = Skill.query.filter_by(name=name).first()
            if not skill:
                skill = Skill(name=name)
                db.session.add(skill)
            skills_objects.append(skill)

        self.required_skills_rel = skills_objects

    def slots_remaining(self) -> int:
        """Return number of available slots (0 if unlimited or full)."""
        if self.slots <= 0:
            return 0
        confirmed = sum(1 for r in self.registrations if r.status in (
            'confirmed', 'completed'))
        return max(0, self.slots - confirmed)


class ExternalParticipant(db.Model):
    """
    A non-PSU (outsider) volunteer who joins specific activities.

    The manuscript treats outsiders as event participants, not system users:
    they are linked to event registrations via a separate record rather than
    being given a privileged (or even login) User account. Public registrations
    receive an internal reference automatically; coordinators may still encode
    legacy or walk-in records with an ID number.
    """
    __tablename__ = 'external_participants'

    id = db.Column(db.Integer, primary_key=True)
    id_number = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)
    email = db.Column(db.String(120), nullable=True)
    sex = db.Column(db.Enum('male', 'female', 'prefer_not_to_say',
                            name='external_participant_sexes'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    registrations = db.relationship(
        'Registration', backref='external_participant', lazy=True,
        cascade='all, delete-orphan')


class Registration(db.Model):
    """
    Tracks volunteer registration for a specific event.
    """
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=True)
    external_participant_id = db.Column(
        db.Integer, db.ForeignKey(
            'external_participants.id', ondelete='SET NULL'), nullable=True)
    event_id = db.Column(db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(
        db.Enum('pending', 'confirmed', 'completed',
                'cancelled', name='registration_statuses'),
        default='pending'
    )
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    policy_accepted_at = db.Column(db.DateTime, nullable=True)
    policy_version = db.Column(db.String(30), nullable=True)
    nda_accepted_at = db.Column(db.DateTime, nullable=True)
    nda_version = db.Column(db.String(30), nullable=True)
    external_privacy_accepted_at = db.Column(db.DateTime, nullable=True)
    external_privacy_version = db.Column(db.String(30), nullable=True)
    attendance_record = db.relationship(
        'Attendance', back_populates='registration', uselist=False,
        passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'event_id', name='uk_user_event'),
        db.UniqueConstraint(
            'external_participant_id', 'event_id', name='uk_external_event'),
        db.CheckConstraint(
            '(user_id IS NOT NULL) OR (external_participant_id IS NOT NULL)',
            name='ck_registration_participant'),
    )

    @property
    def participant(self):
        """Return the linked User (PSU) or ExternalParticipant (outsider)."""
        return self.user or self.external_participant

    @property
    def is_external(self):
        return self.external_participant_id is not None

    @property
    def is_confirmed(self) -> bool:
        return self.status in ('confirmed', 'completed')

    @property
    def certificate_eligible(self) -> bool:
        """Eligibility requires completed participation recorded by attendance."""
        attendance = self.attendance_record
        return bool(
            self.status == 'completed'
            and attendance
            and attendance.status == 'present'
        )


class CancellationRequest(db.Model):
    __tablename__ = 'cancellation_requests'

    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey(
        'registrations.id', ondelete='CASCADE'), nullable=False, unique=True)
    reason = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum('pending', 'approved', 'rejected',
                               name='cancellation_request_statuses'),
                       default='pending', nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='SET NULL'), nullable=True)
    review_note = db.Column(db.Text, nullable=True)

    registration = db.relationship('Registration', backref=db.backref(
        'cancellation_request', uselist=False, cascade='all, delete-orphan'))
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])


class Attendance(db.Model):
    """
    Tracks attendance at an event.
    """
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey(
        'registrations.id', ondelete='CASCADE'), nullable=False, unique=True)
    registration = db.relationship(
        'Registration', back_populates='attendance_record')
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=True)
    event_id = db.Column(db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Enum('present', 'absent', 'excused',
                       name='attendance_statuses'), default='present')
    # Legacy data column retained for migration compatibility. It is no longer
    # collected, calculated, displayed, or exported by the application.
    hours_completed = db.Column(db.Float, default=0.0)


class Milestone(db.Model):
    """
    Stores milestone uploads (photos, documents) for events.
    """
    __tablename__ = 'milestones'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    upload_path = db.Column(db.String(500), default='')
    category = db.Column(db.String(100), default='photo')
    uploaded_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = db.relationship(
        'User', backref=db.backref('uploaded_milestones', lazy=True))


class EventAnnouncement(db.Model):
    """Coordinator update for volunteers registered for an event."""
    __tablename__ = 'event_announcements'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='SET NULL'), nullable=True)
    announcement_type = db.Column(
        db.Enum('last_call', 'event_update', 'cancelled_postponed',
                name='announcement_types'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    author = db.relationship(
        'User', backref=db.backref('event_announcements', lazy=True))


class Campus(db.Model):
    """
    Represents PSU campuses for organizational purposes.
    """
    __tablename__ = 'campuses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, default='')

    def __repr__(self) -> str:
        return f"Campus(id={self.id}, name='{self.name}')"


class ActivityCategory(db.Model):
    """Administrator-managed categories available to volunteer activities."""
    __tablename__ = 'activity_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"ActivityCategory(id={self.id}, name='{self.name}')"


class RecommendationLog(db.Model):
    """
    Logs recommendation system activity for analysis.
    """
    __tablename__ = 'recommendation_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'users.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey(
        'events.id', ondelete='CASCADE'), nullable=False)
    similarity_score = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class AnalyticsSummary(db.Model):
    """
    Pre-calculated aggregate metrics for dashboard performance.
    """
    __tablename__ = 'analytics_summaries'

    id = db.Column(db.Integer, primary_key=True)
    campus_id = db.Column(db.Integer, db.ForeignKey(
        'campuses.id', ondelete='SET NULL'))
    metric_type = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Float, nullable=False)
    period = db.Column(db.String(50), nullable=False)


class HistoricalActivity(db.Model):
    """Aggregate activity imported from legacy institutional reports.

    Historical reports contain aggregate volunteer totals rather than user-level
    registrations and attendance. Keeping them separate prevents fabricated
    users, dates, and capacities from contaminating live data.
    """
    __tablename__ = 'historical_activities'

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    source_document = db.Column(db.String(255), nullable=False)
    source_page = db.Column(db.Integer, nullable=False)
    source_row = db.Column(db.Integer, nullable=False)
    unit_name = db.Column(db.String(120), nullable=False, index=True)
    campus_id = db.Column(db.Integer, db.ForeignKey(
        'campuses.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(500), nullable=False)
    activity_type = db.Column(db.String(30), nullable=True)
    partners = db.Column(db.Text, nullable=True)
    participant_categories = db.Column(db.Text, nullable=True)
    volunteer_count = db.Column(db.Integer, nullable=True)
    year_conducted = db.Column(db.Integer, nullable=True, index=True)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    imported_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    campus = db.relationship('Campus')
    imported_by = db.relationship(
        'User', backref=db.backref('historical_imports', lazy=True))

    __table_args__ = (
        db.CheckConstraint(
            'year_conducted IS NULL OR year_conducted BETWEEN 1900 AND 2100',
            name='ck_historical_activity_year'),
        db.CheckConstraint(
            'volunteer_count IS NULL OR volunteer_count >= 0',
            name='ck_historical_activity_volunteers'),
    )
