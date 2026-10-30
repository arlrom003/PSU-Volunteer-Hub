"""Transactional CSV import using the same rules as goal proposals."""
import csv
import json
from datetime import date
from pathlib import Path

from app.models import db
from app.models.annual_plan import AnnualPlan, AnnualIndicator, AnnualTarget, AnnualResult, AnnualActivityMapping
from app.models.event import Campus, Event
from app.annual_goals import validate_definition, number, cutoff_for, SEX_LABELS
from app.reports import ReportError


def import_file(path, dry_run=False):
    created = unchanged = 0
    try:
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            required = {'plan_key','year','plan_type','plan_title','source_document','indicator_key','indicator_code',
                        'program','indicator_name','unit','responsible_office','target_key','campus_code','target_value'}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ReportError('Missing CSV columns: ' + ', '.join(sorted(missing)))
            seen = set()
            for line, record in enumerate(reader, 2):
                row = {key: (value or '').strip() for key, value in record.items() if key is not None}
                try:
                    for key in ('plan_key', 'indicator_key', 'target_key'):
                        if not row[key] or len(row[key]) > 100:
                            raise ReportError(f'{key} is required (maximum 100 characters).')
                    if row['target_key'] in seen:
                        raise ReportError('Duplicate target_key within this file.')
                    seen.add(row['target_key'])
                    values = validate_definition(dict(row, code=row['indicator_code'], name=row['indicator_name'],
                        definition=row.get('definition') or row['indicator_name'],
                        comparison_rule=row.get('comparison_rule') or 'gte',
                        evidence_basis=row.get('evidence_basis') or 'approved_aggregate'))
                    campus = Campus.query.filter_by(code=row['campus_code']).first() if row['campus_code'] else None
                    if row['campus_code'] and not campus:
                        raise ReportError('Unknown campus_code.')
                    approval = row.get('approval_reference')
                    if not approval:
                        raise ReportError('An approval_reference is required for approved imports.')
                    approval_date = date.fromisoformat(row.get('approval_date', ''))
                    if approval_date > date.today():
                        raise ReportError('Approval date cannot be in the future.')
                    plan_values = dict(year=values['year'], plan_type=values['plan_type'], title=row['plan_title'],
                        source_document=row['source_document'], approval_reference=approval, approval_date=approval_date)
                    if not row['plan_title'] or len(row['plan_title']) > 255 or len(approval) > 120:
                        raise ReportError('Supply a valid plan title and approval reference.')
                    plan = AnnualPlan.query.filter_by(source_key=row['plan_key']).first()
                    if not plan:
                        plan = AnnualPlan(source_key=row['plan_key'], **plan_values)
                        db.session.add(plan); db.session.flush(); created += 1
                    elif any(getattr(plan, key) != value for key, value in plan_values.items()):
                        raise ReportError('Approved plan definitions are immutable; import a new version key.')
                    indicator_values = dict(plan_id=plan.id, code=values['code'], program=values['program'], name=values['name'],
                        definition=values['definition'], unit=values['unit'], responsible_office=values['responsible_office'],
                        evidence_basis=values['evidence_basis'], shared_key=row.get('shared_key') or None)
                    if indicator_values['shared_key'] and len(indicator_values['shared_key']) > 100:
                        raise ReportError('shared_key must contain at most 100 characters.')
                    indicator = AnnualIndicator.query.filter_by(source_key=row['indicator_key']).first()
                    if not indicator:
                        indicator = AnnualIndicator(source_key=row['indicator_key'], **indicator_values)
                        db.session.add(indicator); db.session.flush(); created += 1
                    elif any(getattr(indicator, key) != value for key, value in indicator_values.items()):
                        raise ReportError('Approved indicator definitions are immutable; use a new version key.')
                    target_values = dict(indicator_id=indicator.id, campus_id=campus.id if campus else None,
                        target_value=number(values['target_value']), comparison_rule=values['comparison_rule'],
                        deadline=date.fromisoformat(values['deadline']) if values['deadline'] else None)
                    target = AnnualTarget.query.filter_by(source_key=row['target_key']).first()
                    if not target:
                        target = AnnualTarget(source_key=row['target_key'], **target_values)
                        db.session.add(target); db.session.flush(); created += 1
                    elif any(getattr(target, key) != value for key, value in target_values.items()):
                        raise ReportError('Approved targets are immutable; use a new key and replaces_target_key.')
                    else:
                        unchanged += 1
                    if row.get('replaces_target_key'):
                        previous = AnnualTarget.query.filter_by(source_key=row['replaces_target_key']).first()
                        if not previous or previous.id == target.id or previous.campus_id != target.campus_id or previous.indicator.plan.year != plan.year:
                            raise ReportError('Replacement must reference a different target in the same year and scope.')
                        previous.is_active = False
                    if indicator.shared_key:
                        peers = AnnualTarget.query.join(AnnualIndicator).join(AnnualPlan).filter(
                            AnnualIndicator.shared_key == indicator.shared_key, AnnualPlan.year == plan.year,
                            AnnualTarget.campus_id == target.campus_id, AnnualTarget.is_active.is_(True), AnnualTarget.id != target.id).all()
                        if any((peer.target_value, peer.comparison_rule, peer.indicator.unit, peer.indicator.evidence_basis)
                               != (target.target_value, target.comparison_rule, indicator.unit, indicator.evidence_basis) for peer in peers):
                            raise ReportError('Shared AOP/ASP targets have conflicting definitions.')
                    if row.get('event_ids'):
                        if indicator.evidence_basis == 'approved_aggregate':
                            raise ReportError('Aggregate results cannot also count linked live activities.')
                        ids = {int(value) for value in row['event_ids'].split(';')}
                        events = Event.query.filter(Event.id.in_(ids)).all()
                        if len(events) != len(ids) or any(event.date.year != plan.year or (campus and event.campus_id != campus.id) for event in events):
                            raise ReportError('Linked events must exist in the target year and scope.')
                        existing = {mapping.event_id for mapping in target.activity_mappings}
                        for event_id in ids - existing:
                            db.session.add(AnnualActivityMapping(target_id=target.id, event_id=event_id)); created += 1
                    if row.get('result_key'):
                        if row.get('evidence_status', 'verified') not in ('', 'verified'):
                            raise ReportError('Only verified, approved result snapshots can be imported.')
                        if indicator.evidence_basis != 'approved_aggregate' or row.get('result_type', 'approved_aggregate') != 'approved_aggregate':
                            raise ReportError('Calculated results must come from linked activities, not imported totals.')
                        start = date.fromisoformat(row.get('coverage_start', ''))
                        end = date.fromisoformat(row.get('coverage_end', ''))
                        if start.year != plan.year or end.year != plan.year or start > end or end > cutoff_for(plan.year):
                            raise ReportError('Invalid approved-result coverage.')
                        actual = number(row.get('actual_value'))
                        source = row.get('result_source_document')
                        coverage = row.get('coverage_note')
                        if not source or len(source) > 255 or not coverage or len(coverage) > 4000:
                            raise ReportError('Approved results require a source and coverage explanation.')
                        sex_counts = json.loads(row['sex_counts']) if row.get('sex_counts') else None
                        if sex_counts is not None:
                            if not isinstance(sex_counts, dict) or set(sex_counts) != set(SEX_LABELS) or any(type(value) is not int or value < 0 for value in sex_counts.values()) or sum(sex_counts.values()) != actual:
                                raise ReportError('Sex counts must include all four recorded categories and sum to the approved count. State the counting basis in coverage_note.')
                        result_values = dict(target_id=target.id, actual_value=actual, evidence_status='verified',
                            result_type='approved_aggregate', source_document=source, coverage_note=coverage,
                            coverage_start=start, coverage_end=end, sex_counts=sex_counts)
                        result = AnnualResult.query.filter_by(source_key=row['result_key']).first()
                        if not result:
                            if len(row['result_key']) > 100:
                                raise ReportError('result_key must contain at most 100 characters.')
                            db.session.add(AnnualResult(source_key=row['result_key'], **result_values)); created += 1
                        elif any(getattr(result, key) != value for key, value in result_values.items()):
                            raise ReportError('Approved results are immutable; use a new snapshot result_key.')
                except (ReportError, ValueError, TypeError) as exc:
                    raise ReportError(f'CSV line {line}: {exc}') from None
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return created, unchanged
    except Exception:
        db.session.rollback()
        raise
