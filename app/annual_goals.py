"""Annual goal definitions, scoped evidence, and shared presentation summaries."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from flask_login import current_user
from collections import defaultdict
import operator
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import case, cast, String, func
from flask import has_request_context
from app.performance import request_value
from app.models import db

from app.models.annual_plan import (AnnualPlan, AnnualIndicator, AnnualTarget,
                                   AnnualResult, AnnualGoalProposal, AnnualActivityMapping)
from app.models.event import Campus, Registration, Event, Attendance, ExternalParticipant
from app.models.user import User
from app.reports import ReportError

RULES = {'gte': ('At least', operator.ge), 'lte': ('At most', operator.le), 'eq': ('Exactly', operator.eq)}
BASES = {'approved_aggregate': 'Approved reported result', 'activities': 'Fully recorded ended activities',
         'registrations': 'Non-cancelled registrations', 'verified_attendance': 'Verified attendance occurrences',
         'completed': 'Completed participation occurrences', 'unique_attendees': 'Unique recorded attendees'}
SEX_LABELS = {'female': 'Female', 'male': 'Male', 'prefer_not_to_say': 'Prefer Not to Say', 'unrecorded': 'Not recorded'}


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('1000000000000'):
            raise ValueError()
        if result.as_tuple().exponent < -4:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ReportError('Enter a finite, non-negative number up to 1 trillion, with at most four decimal places.') from None


def selected_year(value=None):
    try:
        year = int(value if value is not None else date.today().year)
        if not 1900 <= year <= 2100:
            raise ValueError()
        return year
    except (TypeError, ValueError):
        raise ReportError('Choose a reporting year from 1900 to 2100.') from None


def validate_definition(data):
    values = {}
    for key, limit in [('program', 255), ('code', 80), ('name', 500), ('definition', 4000),
                       ('unit', 80), ('responsible_office', 255), ('source_document', 255)]:
        value = str(data.get(key, '')).strip()
        if not value or len(value) > limit:
            raise ReportError(f'{key.replace("_", " ").capitalize()} is required (maximum {limit} characters).')
        values[key] = value
    values['year'] = selected_year(data.get('year'))
    values['plan_type'] = data.get('plan_type')
    values['comparison_rule'] = data.get('comparison_rule', 'gte')
    values['evidence_basis'] = data.get('evidence_basis', 'approved_aggregate')
    if values['plan_type'] not in ('AOP', 'ASP') or values['comparison_rule'] not in RULES or values['evidence_basis'] not in BASES:
        raise ReportError('Choose a valid plan, comparison rule, and evidence basis.')
    values['target_value'] = str(number(data.get('target_value')))
    values['deadline'] = str(data.get('deadline', '')).strip()
    if values['deadline']:
        try:
            deadline = date.fromisoformat(values['deadline'])
            if deadline.year != values['year']:
                raise ValueError()
        except ValueError:
            raise ReportError('The deadline must be a valid date in the target year.') from None
    return values


def cutoff_for(year):
    return min(date.today(), date(year, 12, 31))


def registrations(year, campus_id=None, event_ids=None):
    query = Registration.query.join(Event).filter(
        Registration.status != 'cancelled', Event.date >= datetime(year, 1, 1),
        Event.date < datetime.combine(cutoff_for(year), datetime.max.time()))
    if campus_id is not None:
        query = query.filter(Event.campus_id == campus_id)
    if event_ids is not None:
        query = query.filter(Event.id.in_(event_ids))
    return query.options(joinedload(Registration.attendance_record),
                         joinedload(Registration.user),
                         joinedload(Registration.external_participant)).all()


def participation(year, campus_id=None, basis='verified_attendance'):
    counts = dict.fromkeys(SEX_LABELS, 0)
    recorded_sex = case((Registration.user_id.isnot(None), cast(User.sex, String)),
                        else_=cast(ExternalParticipant.sex, String))
    sex = case((recorded_sex.in_(SEX_LABELS), recorded_sex), else_='unrecorded')
    count = _unique_participants() if basis == 'unique_attendees' else func.count(Registration.id)
    query = db.session.query(sex, count).select_from(Registration).join(Event).outerjoin(
        Attendance, Attendance.registration_id == Registration.id).outerjoin(
        User, User.id == Registration.user_id).outerjoin(
        ExternalParticipant, ExternalParticipant.id == Registration.external_participant_id).filter(
        Registration.status != 'cancelled', Event.date >= datetime(year, 1, 1),
        Event.date < datetime.combine(cutoff_for(year), datetime.max.time()))
    if campus_id is not None:
        query = query.filter(Event.campus_id == campus_id)
    if basis != 'registrations':
        query = query.filter(Attendance.status == 'present')
    if basis == 'completed':
        query = query.filter(Registration.status == 'completed')
    counts.update(dict(query.group_by(sex).all()))
    total = sum(counts.values())
    highest = max((counts[key] for key in SEX_LABELS if key != 'unrecorded'), default=0)
    leaders = [SEX_LABELS[key] for key in SEX_LABELS if key != 'unrecorded' and counts[key] == highest] if highest else []
    return dict(counts=[dict(label=SEX_LABELS[key], count=value) for key, value in counts.items()], total=total,
                leader=' / '.join(leaders) if leaders else 'Not available', tie=len(leaders) > 1,
                highest=highest, share=round(highest / total * 100, 1) if total and highest else None,
                basis=BASES[basis], missing=counts['unrecorded'])


def target_row(target, year, evidence=None):
    indicator = target.indicator
    actual, verified, source, coverage = None, False, None, None
    mappings = [mapping.event for mapping in target.activity_mappings]
    results = [result for result in target.results if result.evidence_status == 'verified'
               and result.coverage_end and result.coverage_end <= cutoff_for(year)]
    result = max(results, key=lambda result: (result.coverage_end, result.imported_at, result.id), default=None)
    if indicator.evidence_basis == 'approved_aggregate':
        if result and result.result_type == 'approved_aggregate':
            actual, verified, source, coverage = result.actual_value, True, result.source_document, result.coverage_note
    elif mappings:
        if evidence is None:
            evidence = _activity_evidence([target], year)
        reports, target_counts = evidence
        rows = [reports[event.id] for event in mappings if event.id in reports
                and (target.campus_id is None or event.campus_id == target.campus_id)]
        eligible = [row for row in rows if row['ended']]
        verified = bool(eligible) and all(row['attendance_complete'] for row in eligible)
        registrations_count = sum(row['registrations'] for row in eligible)
        present = sum(row['outcome_attended'] for row in eligible)
        completed = sum(row['verified_completed'] for row in eligible)
        unique = target_counts.get(target.id, 0)
        basis = indicator.evidence_basis
        actual = {'activities': len(eligible), 'registrations': registrations_count, 'verified_attendance': present,
                  'completed': completed, 'unique_attendees': unique}[basis]
        source = 'Linked activity records'
        coverage = f'{len(eligible)} ended activities; complete attendance required for target assessment.'
    if actual is None:
        verified = False
    met = verified and RULES[target.comparison_rule][1](number(actual), number(target.target_value))
    overdue = bool(not met and target.deadline and target.deadline < cutoff_for(year))
    return dict(target_id=target.id, code=indicator.code, name=indicator.name, program=indicator.program,
                definition=indicator.definition, unit=indicator.unit, responsible_office=indicator.responsible_office,
                target=target.target_value, actual=actual, met=bool(met), pending=not verified,
                verified=verified, deadline=target.deadline, overdue=overdue,
                comparison_rule=target.comparison_rule, rule_label=RULES[target.comparison_rule][0],
                plan_types=[indicator.plan.plan_type], plan_type=indicator.plan.plan_type,
                shared_key=indicator.shared_key, basis=BASES[indicator.evidence_basis],
                source_document=source or indicator.plan.source_document, coverage_note=coverage,
                events=[dict(id=event.id, title=event.title) for event in mappings],
                aggregate_sex=result.sex_counts if result and result.result_type == 'approved_aggregate' else None,
                status='Evidence pending' if not verified else 'Target met' if met else 'Targets remaining')


def summarize(rows, year, campus_id=None, sample=False):
    met = sum(row['met'] for row in rows)
    pending = sum(row['pending'] for row in rows)
    plans = {kind: dict(total=sum(kind in row['plan_types'] for row in rows),
                        met=sum(row['met'] and kind in row['plan_types'] for row in rows)) for kind in ('AOP', 'ASP')}
    return dict(year=year, scope='Campus' if campus_id is not None else 'University', campus_id=campus_id,
                total=len(rows), met=met, pending=pending, remaining=len(rows)-met-pending,
                rate=round(met/len(rows)*100, 1) if rows else None, plans=plans, sample=sample,
                cutoff=cutoff_for(year), rows=sorted(rows, key=lambda row: (not row['overdue'], not row['pending'], row['code'])),
                status='No approved targets' if not rows else 'All targets met' if met == len(rows) else 'Evidence pending' if pending else 'Targets remaining')


def _unique_participants():
    return (func.count(func.distinct(Registration.user_id)) +
            func.count(func.distinct(case((Registration.user_id.is_(None),
                                           Registration.external_participant_id)))))


def _activity_evidence(targets, year):
    from app.reports import build_events_report
    event_ids = {mapping.event_id for target in targets
                 if target.indicator.evidence_basis != 'approved_aggregate'
                 for mapping in target.activity_mappings}
    if not event_ids:
        return {}, {}
    rows, _ = build_events_report(event_ids=event_ids, start_date=f'{year}-01-01',
                                  end_date=cutoff_for(year).isoformat(), include_sdgs=False)
    counts = db.session.query(
        AnnualActivityMapping.target_id, _unique_participants(),
    ).join(AnnualTarget, AnnualTarget.id == AnnualActivityMapping.target_id).join(
        Event, Event.id == AnnualActivityMapping.event_id).join(
        Registration, Registration.event_id == Event.id).outerjoin(
        Attendance, Attendance.registration_id == Registration.id).filter(
        AnnualActivityMapping.target_id.in_([target.id for target in targets
                                            if target.indicator.evidence_basis == 'unique_attendees']),
        (AnnualTarget.campus_id.is_(None) | (AnnualTarget.campus_id == Event.campus_id)),
        Event.id.in_([row['event_id'] for row in rows if row['ended']]),
        Registration.status != 'cancelled',
        Attendance.status == 'present',
        Event.date < datetime.combine(cutoff_for(year), datetime.max.time())
    ).group_by(AnnualActivityMapping.target_id).all()
    return {row['event_id']: row for row in rows}, dict(counts)


def _summaries(year, campus_ids):
    targets = AnnualTarget.query.join(AnnualIndicator).join(AnnualPlan).filter(
        AnnualPlan.year == year, AnnualPlan.status == 'approved', AnnualTarget.is_active.is_(True),
        AnnualTarget.campus_id.in_([campus for campus in campus_ids if campus is not None]) |
        (AnnualTarget.campus_id.is_(None) if None in campus_ids else False)
    ).options(joinedload(AnnualTarget.indicator).joinedload(AnnualIndicator.plan),
              joinedload(AnnualTarget.results),
              selectinload(AnnualTarget.activity_mappings).joinedload(AnnualActivityMapping.event).load_only(
                  Event.id, Event.title, Event.campus_id)
    ).order_by(AnnualTarget.id).all()
    evidence = _activity_evidence(targets, year)
    by_campus = defaultdict(list)
    for target in targets:
        by_campus[target.campus_id].append(target)
    return {campus_id: _target_summary(by_campus[campus_id], year, campus_id, evidence)
            for campus_id in campus_ids}


def _target_summary(targets, year, campus_id, activity_evidence):
    groups = defaultdict(list)
    for target in targets:
        groups[target.indicator.shared_key or f'target:{target.id}'].append(target)
    rows = []
    for group in groups.values():
        evidence = [target_row(target, year, activity_evidence) for target in group]
        row = next((item for item in evidence if item['verified']), evidence[0])
        row['plan_types'] = sorted({target.indicator.plan.plan_type for target in group})
        # Conflicting shared definitions cannot support an achievement claim.
        if any((target.target_value, target.comparison_rule, target.indicator.unit, target.indicator.evidence_basis)
               != (group[0].target_value, group[0].comparison_rule, group[0].indicator.unit, group[0].indicator.evidence_basis) for target in group):
            row.update(met=False, verified=False, pending=True, status='Evidence pending', coverage_note='Shared definitions conflict; review imported records.')
        if len({item['actual'] for item in evidence if item['verified']}) > 1:
            row.update(met=False, verified=False, pending=True, status='Evidence pending', coverage_note='Shared target evidence conflicts; review approved results.')
        rows.append(row)
    return summarize(rows, year, campus_id)


def summary(year=None, campus_id=None, sample=False):
    year = selected_year(year)
    if sample:
        return summarize(sample_rows(campus_id), year, campus_id, True)
    if has_request_context() and getattr(current_user, 'role', None) in ('director', 'admin'):
        return dict(_university_summaries(year)[campus_id])
    return _summaries(year, [campus_id])[campus_id]


def _university_summaries(year):
    def load():
        ids = [campus.id for campus in _campuses()]
        return _summaries(year, [None, *ids])
    return request_value(('annual-summaries', year), load)


def _campuses():
    from app.campuses import campus_rows
    return campus_rows()


def sample_rows(campus_id):
    if campus_id is not None and campus_id % 4 == 0:
        return []
    rows = []
    for index, (name, types, target, actual) in enumerate([
        ('Community learning activities', ['AOP'], 8, 8),
        ('Completed outreach programs', ['ASP'], 4, 3),
        ('Partner-supported programs', ['AOP', 'ASP'], 3, 3),
        ('Verified participation occurrences', ['AOP'], 120, None)]):
        if campus_id and campus_id % 3 == 0:
            actual = target
        elif campus_id and campus_id % 2 == 0 and actual is None:
            actual = target - 1
        rows.append(dict(target_id=None, code=f'SAMPLE-{index+1}', name=name, program='Sample extension program',
                         definition='Illustrative definition for dashboard review only.', unit='participation occurrences' if index == 3 else 'programs',
                         responsible_office='Sample Extension Office', target=target, actual=actual,
                         met=actual is not None and actual >= target, pending=actual is None, verified=actual is not None,
                         deadline=None, overdue=False, rule_label='At least', comparison_rule='gte', plan_types=types,
                         source_document='Sample data; no institutional approval', coverage_note='Illustrative results only.',
                         events=[], aggregate_sex=None, basis='Sample approved aggregate',
                         status='Evidence pending' if actual is None else 'Target met' if actual >= target else 'Targets remaining'))
    return rows


def comparisons(year=None, sample=False):
    year = selected_year(year)
    campuses = _campuses()
    plans = ({campus.id: summarize(sample_rows(campus.id), year, campus.id, True) for campus in campuses}
             if sample else _university_summaries(year))
    return [dict(plans[campus.id], campus=campus.name) for campus in campuses]


def campus_ranking(campuses, lowest=False):
    """Rank the existing summaries by exact achievement ratios, retaining ties."""
    rows = sorted((campus for campus in campuses if campus['total'] > 0),
                  key=lambda campus: ((1 if lowest else -1) * Fraction(campus['met'], campus['total']),
                                      campus['campus'].casefold(), campus['campus_id']))
    if not rows:
        return dict(state='unavailable', rows=[], leaders=[])
    best = Fraction(rows[0]['met'], rows[0]['total'])
    leaders = [campus for campus in rows if Fraction(campus['met'], campus['total']) == best] if best or lowest else []
    return dict(state='ranked' if leaders else 'zero', rows=rows, leaders=leaders)


def goal_guidance(plan):
    """Remaining goals are not overdue unless an approved deadline says so."""
    if plan.get('sample'):
        return []
    if not plan['total']:
        code, priority, text = 'no_targets', 2, 'Submit or review campus goal proposals before interpreting annual performance.'
    elif plan['met'] < plan['total']:
        code, priority, text = 'remaining_goals', 6, 'Review remaining campus goals and agree on the next evidence or activity milestone.'
    else:
        return []
    return [dict(code=code, priority=priority, text=text, event_id=None,
                 evidence=f'{plan["met"]} of {plan["total"]} approved goals achieved; {plan["pending"]} awaiting evidence.',
                 scope_label=f'Annual goal year {plan["year"]}; independent of report filters.')]


def dashboard_context(year=None, campus_id=None):
    from flask import request, url_for
    year = selected_year(request.args.get('goal_year', year))
    sample = request.args.get('sample') == '1'
    plan = summary(year, campus_id, sample)
    if campus_id is None:
        lowest = request.endpoint == 'director.director_dash' and getattr(current_user, 'role', None) == 'director'
        plan['campus_summaries'] = comparisons(year, sample)
        if request.endpoint == 'director.director_dash':
            rollup = summarize([row for campus in plan['campus_summaries'] for row in campus['rows']],
                               year, sample=sample)
            rollup.update(scope='All Campus',
                          detail_url=url_for('goals.details', year=year, sample=1 if sample else None,
                                             _anchor='campus-results'),
                          aop_url=url_for('goals.details', year=year, plan='AOP',
                                          sample=1 if sample else None, _anchor='campus-results'),
                          asp_url=url_for('goals.details', year=year, plan='ASP',
                                          sample=1 if sample else None, _anchor='campus-results'))
            plan['campus_rollup'] = rollup
        ranking = campus_ranking(plan['campus_summaries'], lowest=lowest)
        for campus in ranking['rows']:
            campus['detail_url'] = url_for('goals.details', year=year, campus=campus['campus_id'],
                                           sample=1 if sample else None)
            campus['is_lowest'] = campus in ranking['leaders'] if lowest else False
        plan['campus_ranking'] = ranking
    else:
        plan['participation'] = participation(year, campus_id)
        from app.dashboard import present_guidance
        plan['guidance'] = present_guidance(goal_guidance(plan), campus_id, year)
    plan['detail_url'] = url_for('goals.details', year=year, sample=1 if sample else None)
    plan['aop_url'] = url_for('goals.details', year=year, plan='AOP', sample=1 if sample else None)
    plan['asp_url'] = url_for('goals.details', year=year, plan='ASP', sample=1 if sample else None)
    plan['workspace_url'] = url_for('goals.workspace')
    proposals = AnnualGoalProposal.query
    if campus_id is not None:
        proposals = proposals.filter_by(campus_id=campus_id)
    else:
        proposals = proposals.filter_by(status='submitted')
    plan['proposal_count'] = proposals.filter(AnnualGoalProposal.status.in_(['draft', 'submitted', 'returned'])).count()
    return plan
