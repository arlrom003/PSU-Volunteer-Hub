"""Role-scoped goal evidence and proposal review. All mutations require POST/CSRF."""
import csv
import io
from datetime import date, datetime
from math import ceil
from xml.sax.saxutils import escape

from flask import Blueprint, abort, flash, redirect, render_template, request, Response, url_for
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.pagination import paginate

from app.models import db
from app.campuses import campus_query
from app.models.annual_plan import (AnnualPlan, AnnualIndicator, AnnualTarget, AnnualResult,
                                   AnnualActivityMapping, AnnualGoalProposal)
from app.models.event import Campus, Event
from app.utils.decorators import roles_required
from app.annual_goals import (summary, comparisons, participation, validate_definition, selected_year,
                              number, RULES, BASES, cutoff_for)
from app.reports import ReportError, csv_safe

goals_bp = Blueprint('goals', __name__, url_prefix='/annual-goals')


@goals_bp.app_template_filter('goal_number')
def goal_number(value):
    """Format validated goal numbers without trailing decimal zeros; preserve unknowns."""
    if value is None:
        return 'Not available'
    text = format(number(value), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def director():
    """Check exact director role; read-capable admins are not goal publishers here."""
    return current_user.role == 'director'


def campus_scope():
    """Resolve reader scope without accepting a coordinator's requested campus.

    Director/admin may choose an existing campus or separate university targets.
    Coordinators always use assigned campus; missing assignment returns 403.
    """
    if current_user.role in ('director', 'admin'):
        value = request.args.get('campus', '')
        if not value:
            return None
        try:
            campus = db.session.get(Campus, int(value))
        except ValueError:
            campus = None
        if campus is None:
            abort(400, description='Choose an available campus.')
        return campus.id
    if current_user.campus_id is None:
        abort(403)
    return current_user.campus_id


def reject_sample_write():
    """Reject sample=1 on query/form so preview data cannot become official writes."""
    if request.args.get('sample') == '1' or request.form.get('sample') == '1':
        abort(400, description='Sample previews are read-only. Exit the preview to manage official goals.')


def owned_proposal(proposal_id, lock=False):
    """Load proposal or 404; restrict non-directors to their assigned campus.

    Mutation callers request a row lock to serialize edits and review decisions
    on databases supporting FOR UPDATE. Route decorators enforce allowed roles.
    """
    statement = select(AnnualGoalProposal).where(AnnualGoalProposal.id == proposal_id)
    if lock:
        statement = statement.with_for_update()
    proposal = db.session.execute(statement).scalar_one_or_none()
    if proposal is None:
        abort(404)
    if not director() and (current_user.campus_id is None or proposal.campus_id != current_user.campus_id):
        abort(403)
    return proposal


def history(proposal, action, note=None):
    """Append actor, UTC time, note, and payload snapshot to proposal audit history.

    Replace JSON list so ORM tracks the update; caller owns commit/rollback.
    """
    proposal.history = [*(proposal.history or []), dict(action=action, actor=current_user.id,
                       at=datetime.utcnow().isoformat(), note=note, payload=dict(proposal.payload))]


@goals_bp.route('')
@login_required
@roles_required('coordinator', 'director', 'admin')
def details():
    """Show approved goal results with scoped filters and ten rows per page.

    Export all filtered rows before pagination. Block official exports of sample
    figures. Participation basis affects demographic counts, not target evidence.
    Campus comparison cards recalculate plan/program/office selections separately;
    status filtering applies to main detail rows.
    """
    try:
        year = selected_year(request.args.get('year'))
    except ReportError as exc:
        abort(400, description=str(exc))
    campus_id = campus_scope()
    sample = request.args.get('sample') == '1'
    plan = summary(year, campus_id, sample)
    rows = plan['rows']
    filters = {key: request.args.get(key, '').strip() for key in ('plan', 'program', 'office', 'status')}
    if filters['plan'] not in ('', 'AOP', 'ASP') or filters['status'] not in ('', 'met', 'remaining', 'pending'):
        abort(400, description='Choose valid goal filters.')
    programs = sorted({row['program'] for row in rows})
    offices = sorted({row['responsible_office'] for row in rows})
    for key, field in [('program', 'program'), ('office', 'responsible_office')]:
        if filters[key]:
            rows = [row for row in rows if row[field] == filters[key]]
    if filters['plan']:
        rows = [row for row in rows if filters['plan'] in row['plan_types']]
    if filters['status']:
        rows = [row for row in rows if (row['met'] if filters['status'] == 'met' else row['pending'] if filters['status'] == 'pending' else row['verified'] and not row['met'])]
    basis = request.args.get('basis', 'verified_attendance')
    if basis not in ('registrations', 'verified_attendance', 'completed', 'unique_attendees'):
        abort(400, description='Choose a valid participation counting basis.')
    export = request.args.get('export')
    if export:
        if sample:
            abort(400, description='Sample figures cannot be exported as official results.')
        return export_rows(rows, plan, filters, export)
    pages = max(1, ceil(len(rows) / 10))
    page = min(max(request.args.get('page', 1, type=int), 1), pages)
    query = request.args.to_dict()
    query.pop('page', None)
    university_reader = current_user.role in ('director', 'admin')
    campus_rows = comparisons(year, sample) if university_reader else []
    # Campus cards apply plan/program/office filters; main rows also apply status.
    from app.annual_goals import summarize
    for campus in campus_rows:
        selected = [row for row in campus['rows']
                    if (not filters['plan'] or filters['plan'] in row['plan_types'])
                    and (not filters['program'] or row['program'] == filters['program'])
                    and (not filters['office'] or row['responsible_office'] == filters['office'])]
        updated = summarize(selected, year, campus['campus_id'], sample)
        campus.update(updated)
    return render_template('goals/details.html', plan=plan, rows=rows[(page-1)*10:page*10],
        row_count=len(rows), page=page, pages=pages, query=query, filters=filters, programs=programs,
        offices=offices, campuses=campus_query().order_by(Campus.name).all() if university_reader else [],
        campus_rows=campus_rows, participation=participation(year, campus_id, basis), basis=basis,
        director=university_reader, sample=sample, campus_id=campus_id,
        scope_name=(db.session.get(Campus, campus_id).name + ' campus') if campus_id is not None else 'University')


def export_rows(rows, plan, filters, kind):
    """Format supplied goal evidence as CSV/PDF with source, coverage, and scope.

    Export caller's full filtered set, not page slice. Protect spreadsheet text
    with csv_safe and escape PDF Paragraph text; reject unsupported formats.
    """
    if kind not in ('csv', 'pdf'):
        abort(400)
    columns = ['Code', 'Indicator', 'Plans', 'Program', 'Actual', 'Target', 'Unit', 'Rule', 'Office', 'Status', 'Source', 'Coverage']
    data = [[row['code'], row['name'], '/'.join(row['plan_types']), row['program'],
             row['actual'] if row['actual'] is not None else 'Not available', row['target'], row['unit'],
             row['rule_label'], row['responsible_office'], row['status'], row['source_document'], row['coverage_note'] or ''] for row in rows]
    scope = f"{plan['scope']} targets; campus={plan['campus_id'] or 'university'}; year={plan['year']}; cutoff={plan['cutoff']}; filters={filters}"
    if kind == 'csv':
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['Annual goal evidence', csv_safe(scope)])
        writer.writerow(columns)
        writer.writerows([[csv_safe(value) for value in record] for record in data])
        body, mime = stream.getvalue(), 'text/csv'
    else:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        story = [Paragraph('Annual goal evidence', styles['Title']), Paragraph(escape(scope), styles['BodyText'])]
        for record in data:
            story.extend([Spacer(1, 14), Paragraph(escape(str(record[0]) + ': ' + str(record[1])), styles['Heading2'])])
            for label, value in zip(columns[2:], record[2:]):
                story.append(Paragraph(escape(f'{label}: {value}'), styles['BodyText']))
        if not data:
            story.append(Paragraph('No approved targets match these filters.', styles['BodyText']))
        SimpleDocTemplate(buffer, pagesize=A4).build(story)
        body, mime = buffer.getvalue(), 'application/pdf'
    return Response(body, mimetype=mime, headers={'Content-Disposition': f'attachment; filename=annual-goals-{plan["year"]}.{kind}'})


@goals_bp.route('/workspace')
@login_required
@roles_required('coordinator', 'director')
def workspace():
    """List coordinator's campus proposals or director's reviewable/university work.

    Coordinators cannot inspect other campuses. Directors see submitted,
    returned, approved campus proposals plus university drafts; newest first.
    """
    query = AnnualGoalProposal.query
    if not director():
        if current_user.campus_id is None:
            abort(403)
        query = query.filter_by(campus_id=current_user.campus_id)
    else:
        query = query.filter((AnnualGoalProposal.status.in_(['submitted', 'returned', 'approved'])) |
                             (AnnualGoalProposal.campus_id.is_(None)))
    return render_template('goals/workspace.html', proposals=query.order_by(AnnualGoalProposal.created_at.desc()).all(), director=director())


@goals_bp.route('/proposals/new', methods=['GET', 'POST'])
@goals_bp.route('/proposals/<int:proposal_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('coordinator', 'director')
def edit(proposal_id=None):
    """Create/edit drafts and returned proposals, then save, submit, or publish.

    Coordinators work only on their campus; simplified new goals default to
    completed activities and require whole-number targets. Existing definitions
    retain hidden values. Directors create/edit university proposals and can
    publish directly. Revisions must reference active targets in matching scope.
    Validate before saving, append history, and commit publication atomically.
    """
    reject_sample_write()
    proposal = owned_proposal(proposal_id, lock=request.method == 'POST') if proposal_id else None
    if proposal and proposal.status not in ('draft', 'returned'):
        abort(409, description='Only draft or returned proposals can be edited.')
    if director() and proposal and proposal.campus_id is not None:
        abort(403)
    if not director() and current_user.campus_id is None:
        abort(403)
    values = dict(proposal.payload) if proposal else {}
    if not director() and not proposal:
        values = dict(year=date.today().year, plan_type='AOP',
                      program='Campus extension activities', code='COMPLETED-ACTIVITIES',
                      name='Completed activities',
                      definition='Count linked activities that have ended, with complete attendance records required for assessment.',
                      unit='activities', evidence_basis='activities', comparison_rule='gte',
                      source_document='PSU Volunteer Hub campus goal proposal', deadline='')
    replacement = None
    raw_replacement = request.args.get('revise', '') if not proposal else proposal.replaces_target_id
    if raw_replacement:
        replacement = db.session.get(AnnualTarget, int(raw_replacement)) if str(raw_replacement).isdigit() else None
        expected_campus = None if director() else current_user.campus_id
        if replacement is None or replacement.campus_id != expected_campus:
            abort(403)
        if not replacement.is_active:
            abort(409, description='This target has already been replaced.')
        if not proposal:
            indicator = replacement.indicator
            values = dict(year=indicator.plan.year, plan_type=indicator.plan.plan_type, program=indicator.program,
                          code=indicator.code, name=indicator.name, definition=indicator.definition or '',
                          target_value=replacement.target_value, unit=indicator.unit, comparison_rule=replacement.comparison_rule,
                          responsible_office=indicator.responsible_office, source_document=indicator.plan.source_document,
                          deadline=replacement.deadline.isoformat() if replacement.deadline else '', evidence_basis=indicator.evidence_basis)
    error = None
    if request.method == 'POST':
        values = {**values, **request.form.to_dict()} if not director() else request.form.to_dict()
        try:
            cleaned = validate_definition(values)
            if not director() and cleaned['evidence_basis'] == 'activities':
                target_value = number(cleaned['target_value'])
                if target_value != target_value.to_integral_value():
                    raise ReportError('Enter a whole number of completed activities.')
            action = request.form.get('action', 'save')
            if action not in ('save', 'submit', 'publish') or (action == 'publish' and not director()):
                abort(400)
            if not proposal:
                proposal = AnnualGoalProposal(campus_id=None if director() else current_user.campus_id,
                    proposed_by_id=current_user.id, replaces_target_id=replacement.id if replacement else None,
                    payload=cleaned, history=[])
                db.session.add(proposal)
            proposal.payload = cleaned
            if action == 'submit':
                proposal.status = 'submitted'
                proposal.submitted_at = datetime.utcnow()
            history(proposal, 'submitted' if action == 'submit' else 'saved')
            db.session.flush()
            if action == 'publish':
                publish(proposal)
            db.session.commit()
            flash('Goal published.' if action == 'publish' else 'Proposal submitted for director review.' if action == 'submit' else 'Draft saved.', 'success')
            return redirect(url_for('goals.workspace'))
        except ReportError as exc:
            db.session.rollback()
            error = str(exc)
    return render_template('goals/edit.html', values=values, proposal=proposal, error=error, director=director(), rules=RULES, bases=BASES), 400 if error else 200


def publish(proposal):
    """Create approved plan/indicator/target records from validated proposal data.

    Caller enforces director permission and commits. Lock replacement targets;
    reject stale/inactive, wrong-campus, or wrong-year revisions. Retire replaced
    targets instead of erasing history. Shared AOP/ASP revisions retire active
    peers and create matching new definitions for all linked plan types.
    Mark proposal approved and record reviewer/history in the same transaction.
    """
    payload = validate_definition(proposal.payload)
    replacement = None
    if proposal.replaces_target_id:
        replacement = db.session.execute(select(AnnualTarget).where(
            AnnualTarget.id == proposal.replaces_target_id).with_for_update()).scalar_one()
        if not replacement.is_active or replacement.campus_id != proposal.campus_id or replacement.indicator.plan.year != payload['year']:
            raise ReportError('The approved goal has changed. Create a revision from its current version.')
    plan_types = {payload['plan_type']}
    shared_key = replacement.indicator.shared_key if replacement else None
    if shared_key:
        peers = AnnualTarget.query.join(AnnualIndicator).join(AnnualPlan).filter(
            AnnualIndicator.shared_key == shared_key, AnnualPlan.year == payload['year'],
            AnnualTarget.campus_id == proposal.campus_id, AnnualTarget.is_active.is_(True)).with_for_update().all()
        plan_types.update(peer.indicator.plan.plan_type for peer in peers)
        for peer in peers:
            peer.is_active = False
    elif replacement:
        replacement.is_active = False
    published = []
    for kind in sorted(plan_types):
        key = f'proposal:{proposal.id}:{kind}'
        plan = AnnualPlan(source_key=key, year=payload['year'], plan_type=kind,
            title=f"{payload['year']} {kind} approved goal", source_document=payload['source_document'],
            approval_reference=f'Director {current_user.id}; proposal {proposal.id}', approval_date=date.today())
        db.session.add(plan)
        db.session.flush()
        indicator = AnnualIndicator(source_key=key, plan_id=plan.id, code=payload['code'], program=payload['program'],
            name=payload['name'], definition=payload['definition'], unit=payload['unit'], responsible_office=payload['responsible_office'],
            evidence_basis=payload['evidence_basis'], shared_key=shared_key)
        db.session.add(indicator)
        db.session.flush()
        target = AnnualTarget(source_key=key, indicator_id=indicator.id, campus_id=proposal.campus_id,
            target_value=number(payload['target_value']), comparison_rule=payload['comparison_rule'],
            deadline=date.fromisoformat(payload['deadline']) if payload['deadline'] else None)
        db.session.add(target)
        db.session.flush()
        published.append(target)
    proposal.status = 'approved'
    proposal.published_target_id = published[0].id
    proposal.reviewed_by_id = current_user.id
    proposal.reviewed_at = datetime.utcnow()
    history(proposal, 'approved')


@goals_bp.route('/proposals/<int:proposal_id>', methods=['GET', 'POST'])
@login_required
@roles_required('coordinator', 'director')
def review(proposal_id):
    """Let director approve or return a submitted campus proposal exactly once.

    Lock POST review, require submitted status, and reject preview writes.
    Returning requires explanation; approval publishes official targets.
    Ownership permits coordinator read access, but only director can decide.
    Save decision/note/history together; validation errors roll back changes.
    """
    proposal = owned_proposal(proposal_id, lock=request.method == 'POST')
    error = None
    if request.method == 'POST':
        reject_sample_write()
        if not director():
            abort(403)
        if proposal.status != 'submitted':
            abort(409, description='This proposal is no longer awaiting review.')
        try:
            action = request.form.get('action')
            note = request.form.get('note', '').strip()
            if len(note) > 4000:
                raise ReportError('Review notes must contain at most 4000 characters.')
            if action == 'return':
                if not note:
                    raise ReportError('Explain what the coordinator must revise.')
                proposal.status = 'returned'
                proposal.reviewed_by_id = current_user.id
                proposal.reviewed_at = datetime.utcnow()
                history(proposal, 'returned', note)
            elif action == 'approve':
                publish(proposal)
            else:
                abort(400)
            proposal.review_note = note or None
            db.session.commit()
            flash('Proposal approved.' if action == 'approve' else 'Proposal returned for revision.', 'success')
            return redirect(url_for('goals.workspace'))
        except ReportError as exc:
            db.session.rollback()
            error = str(exc)
    return render_template('goals/review.html', proposal=proposal, director=director(),
                           error=error, rules=RULES, bases=BASES), 400 if error else 200


@goals_bp.route('/targets/<int:target_id>/activities')
@login_required
@roles_required('coordinator', 'director', 'admin')
def target_activities(target_id):
    """Show paginated mapped activities in target year and campus scope.

    Coordinators must own target campus. Listing includes upcoming mappings;
    target assessment separately checks cutoff, ended state, and attendance.
    """
    target = db.get_or_404(AnnualTarget, target_id)
    if current_user.role == 'coordinator' and target.campus_id != current_user.campus_id:
        abort(403)
    year = target.indicator.plan.year
    query = Event.query.join(AnnualActivityMapping).filter(
        AnnualActivityMapping.target_id == target.id,
        Event.date >= datetime(year, 1, 1), Event.date < datetime(year+1, 1, 1))
    if target.campus_id is not None:
        query = query.filter(Event.campus_id == target.campus_id)
    pagination = paginate(query.options(joinedload(Event.campus)).order_by(Event.date.desc(), Event.id.desc()))
    return render_template('goals/activities.html', target=target, pagination=pagination,
                           activities=pagination.items, year=year)


@goals_bp.route('/targets/<int:target_id>/evidence', methods=['GET', 'POST'])
@login_required
@roles_required('director')
def evidence(target_id):
    """Let director attach evidence to an active target; previews cannot write.

    Live basis replaces activity mappings after checking target year/campus.
    Aggregate basis appends an approved snapshot with source and coverage note;
    dates must be ordered, in target year, and through cutoff. Earlier snapshots
    stay stored; assessment selects latest eligible snapshot instead of summing.
    Commit only validated changes; failed validation rolls back the transaction.
    """
    reject_sample_write()
    target = db.get_or_404(AnnualTarget, target_id)
    if not target.is_active:
        abort(409)
    error = None
    if request.method == 'POST':
        try:
            year = target.indicator.plan.year
            if target.indicator.evidence_basis != 'approved_aggregate':
                ids = request.form.getlist('event_id', type=int)
                events = Event.query.filter(Event.id.in_(ids)).all()
                if len(set(ids)) != len(events) or any((target.campus_id is not None and event.campus_id != target.campus_id) or event.date.year != year for event in events):
                    raise ReportError('Choose activities in the target year and campus scope.')
                AnnualActivityMapping.query.filter_by(target_id=target.id).delete()
                db.session.add_all([AnnualActivityMapping(target_id=target.id, event_id=event.id) for event in events])
            else:
                try:
                    start, end = date.fromisoformat(request.form.get('coverage_start', '')), date.fromisoformat(request.form.get('coverage_end', ''))
                except ValueError:
                    raise ReportError('Enter valid coverage start and end dates.') from None
                if start.year != year or end.year != year or start > end or end > cutoff_for(year):
                    raise ReportError('Evidence coverage must be within the target year and through today.')
                source = request.form.get('source_document', '').strip()
                note = request.form.get('coverage_note', '').strip()
                if not source or len(source) > 255 or not note or len(note) > 4000:
                    raise ReportError('Provide an approval/source reference and coverage explanation.')
                actual = number(request.form.get('actual_value'))
                if not request.form.get('approved'):
                    raise ReportError('Confirm that this is an approved result for the stated coverage.')
                db.session.add(AnnualResult(source_key=f'evidence:{target.id}:{datetime.utcnow().isoformat()}',
                    target_id=target.id, actual_value=actual, evidence_status='verified', result_type='approved_aggregate',
                    source_document=source, coverage_note=note, coverage_start=start, coverage_end=end))
            db.session.commit()
            flash('Evidence saved. Approved aggregate snapshots replace earlier snapshots; they are never added together.', 'success')
            return redirect(url_for('goals.details', year=year, campus=target.campus_id))
        except ReportError as exc:
            db.session.rollback()
            error = str(exc)
    events = Event.query.filter(db.extract('year', Event.date) == target.indicator.plan.year)
    if target.campus_id is not None:
        events = events.filter_by(campus_id=target.campus_id)
    return render_template('goals/evidence.html', target=target, events=events.order_by(Event.date).all(),
        selected={mapping.event_id for mapping in target.activity_mappings}, error=error), 400 if error else 200
