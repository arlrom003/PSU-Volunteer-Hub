"""Approved annual operational and strategic plan records."""
from datetime import datetime
from app.models import db


class AnnualPlan(db.Model):
    __tablename__ = 'annual_plans'
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(100), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    plan_type = db.Column(db.Enum('AOP', 'ASP', name='annual_plan_types'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Enum('approved', 'superseded', name='annual_plan_statuses'),
                       nullable=False, default='approved')
    source_document = db.Column(db.String(255), nullable=False)
    approval_reference = db.Column(db.String(120), nullable=True)
    approval_date = db.Column(db.Date, nullable=True)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    indicators = db.relationship('AnnualIndicator', backref='plan', lazy=True,
                                 cascade='all, delete-orphan')


class AnnualIndicator(db.Model):
    __tablename__ = 'annual_indicators'
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(100), unique=True, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('annual_plans.id', ondelete='CASCADE'), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    program = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    definition = db.Column(db.Text, nullable=True)
    unit = db.Column(db.String(80), nullable=False)
    responsible_office = db.Column(db.String(255), nullable=False)
    evidence_basis = db.Column(db.String(80), nullable=False, default='verified_attendance')
    shared_key = db.Column(db.String(100), nullable=True, index=True)

    targets = db.relationship('AnnualTarget', backref='indicator', lazy=True,
                              cascade='all, delete-orphan')


class AnnualTarget(db.Model):
    __tablename__ = 'annual_targets'
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(100), unique=True, nullable=False)
    indicator_id = db.Column(db.Integer, db.ForeignKey('annual_indicators.id', ondelete='CASCADE'), nullable=False)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='RESTRICT'), nullable=True)
    target_value = db.Column(db.Numeric(18, 4), nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    activity_scope = db.Column(db.String(80), nullable=True)
    comparison_rule = db.Column(db.String(4), nullable=False, default='gte')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    campus = db.relationship('Campus')
    results = db.relationship('AnnualResult', backref='target', lazy=True,
                              cascade='all, delete-orphan')


class AnnualResult(db.Model):
    __tablename__ = 'annual_results'
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(100), unique=True, nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey('annual_targets.id', ondelete='CASCADE'), nullable=False)
    actual_value = db.Column(db.Numeric(18, 4), nullable=True)
    evidence_status = db.Column(db.Enum('pending', 'verified', name='annual_evidence_statuses'),
                                nullable=False, default='pending')
    result_type = db.Column(db.Enum('calculated', 'approved_aggregate', name='annual_result_types'),
                            nullable=False)
    source_document = db.Column(db.String(255), nullable=True)
    coverage_note = db.Column(db.Text, nullable=True)
    coverage_start = db.Column(db.Date, nullable=True)
    coverage_end = db.Column(db.Date, nullable=True)
    sex_counts = db.Column(db.JSON, nullable=True)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AnnualActivityMapping(db.Model):
    __tablename__ = 'annual_activity_mappings'
    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey('annual_targets.id', ondelete='CASCADE'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='RESTRICT'), nullable=False)
    target = db.relationship('AnnualTarget', backref='activity_mappings')
    event = db.relationship('Event')
    __table_args__ = (db.UniqueConstraint('target_id', 'event_id', name='uq_annual_target_event'),)


class AnnualGoalProposal(db.Model):
    __tablename__ = 'annual_goal_proposals'
    id = db.Column(db.Integer, primary_key=True)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='RESTRICT'), nullable=True)
    replaces_target_id = db.Column(db.Integer, db.ForeignKey('annual_targets.id', ondelete='RESTRICT'), nullable=True)
    published_target_id = db.Column(db.Integer, db.ForeignKey('annual_targets.id', ondelete='RESTRICT'), nullable=True)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(16), nullable=False, default='draft')
    proposed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.Text, nullable=True)
    history = db.Column(db.JSON, nullable=False, default=list)
    campus = db.relationship('Campus')
