"""
Director Routes for PSU Volunteer Hub
========================================
Manages director dashboard and analytics views.
Uses AnalyticsAggregator for all aggregation queries.
"""
import csv
import io
from collections import Counter
from calendar import Calendar
from datetime import datetime
from flask import Blueprint, render_template, Response, current_app, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app.utils.decorators import roles_required
from app.recommendation.analytics import AnalyticsAggregator
from app.models import db
from app.models.event import Event, Campus, SdgGoal
from app.models.user import User
from sqlalchemy.orm import selectinload
from app.dashboard import summarize_report, resolve_period, dashboard_evidence, annual_plan_summary
from app.reports import (
    build_events_report, render_csv, render_pdf, resolve_campus,
    ReportError, _build_meta, parse_date_range)

director_bp = Blueprint('director', __name__, url_prefix='')


def _live_campuses(campuses):
    """Resolve only the live scope; legacy campus_id remains compatible."""
    mode = request.args.get('campus_mode', 'include')
    raw = [value.strip() for value in request.args.getlist('campus') if value.strip()]
    values = request.args.getlist('campus', type=int)
    available = {campus.id for campus in campuses}
    selected = set(values) & available
    error = None
    if len(values) != len(raw) or not set(values) <= available:
        error = 'Some campus choices are unavailable. Choose campuses from the list and apply filters again.'
    if mode not in ('include', 'exclude'):
        error = 'Choose whether to show only or exclude selected campuses, then apply filters again.'
        mode = 'include'
    if 'campus' not in request.args and 'campus_mode' not in request.args:
        legacy = resolve_campus(request.args.get('campus_id'))
        selected = {legacy} if legacy else set()
    if error:
        allowed = []
    elif not selected:
        allowed = None
    elif mode == 'exclude':
        allowed = sorted(available - selected) + [None]
    else:
        allowed = sorted(selected)
    return sorted(selected), mode, allowed, error


def _historical_filters():
    return {
        'campus_id': request.args.get('campus_id', type=int),
        'start_year': request.args.get('start_year', type=int),
        'end_year': request.args.get('end_year', type=int),
        'activity_type': request.args.get('activity_type', '').strip() or None,
    }


def _live_report_context(period):
    campuses = Campus.query.order_by(db.func.lower(Campus.name), Campus.name, Campus.id).all()
    selected, mode, allowed, error = _live_campuses(campuses)
    sex = request.args.get('sex', '').strip().lower()
    sex = sex if sex in ('male', 'female', 'prefer_not_to_say', 'unrecorded') else None
    sdgs = SdgGoal.query.order_by(SdgGoal.number).all()
    sdg_id = request.args.get('sdg_id', type=int)
    sdg = next((goal for goal in sdgs if goal.id == sdg_id), None)
    sdg_id = sdg.id if sdg else None
    try:
        evidence = dashboard_evidence(dict(campus_ids=allowed,
            category=request.args.get('category', '').strip(), sex=sex, sdg_id=sdg_id,
            activity_name=request.args.get('activity_name', ''),
            attention=request.args.get('attention', ''), event_id=request.args.get('event_id')), period)
    except ReportError:
        abort(400, description='Choose valid report dates and attention filters. Clear the sex filter to review participant targets.')
    query = {key: values for key, values in request.args.to_dict(flat=False).items()
             if key not in {'view', 'page', 'start_year', 'end_year', 'activity_type'}}
    query.update(start_date=[period['start']], end_date=[period['end']])
    if not error:
        query.update(campus=[str(campus_id) for campus_id in selected], campus_mode=[mode])
    departments = db.session.query(User.college_affiliation).filter(User.college_affiliation.isnot(None))
    home_campus = request.args.get('campus_id', type=int)
    if home_campus:
        departments = departments.filter(User.campus_id == home_campus)
    scope = [period['label']]
    names = [campus.name for campus in campuses if campus.id in selected]
    scope.append('Invalid Campus Selection' if error else
                 (('All campuses except: ' if mode == 'exclude' else 'Selected campuses: ') +
                  ', '.join(names) if names else 'All campuses'))
    for key, label in [('activity_name', 'Activity'), ('category', 'Category')]:
        if request.args.get(key):
            scope.append(f"{label}: {request.args[key]}")
    if sex:
        scope.append('Sex: ' + {'female': 'Female', 'male': 'Male',
            'prefer_not_to_say': 'Prefer Not to Say', 'unrecorded': 'Not Recorded'}[sex])
    if sdg_id:
        scope.append(f'SDG: {sdg.number}, {sdg.name}')
    if request.args.get('attention'):
        scope.append('Attention: ' + evidence['attention_labels'][request.args['attention']])

    def _without(*keys):
        return {key: value for key, value in query.items() if key not in keys}

    chips = []
    if request.args.get('activity_name', '').strip():
        chips.append({'label': 'Activity: ' + request.args['activity_name'].strip(),
                      'query': _without('activity_name')})
    if request.args.get('category', '').strip():
        chips.append({'label': 'Category: ' + request.args['category'].strip(),
                      'query': _without('category')})
    if names and not error:
        chips.append({'label': (('All campuses except ' if mode == 'exclude' else 'Campuses: ')
                                + ', '.join(names)), 'query': _without('campus', 'campus_mode')})
    if sex:
        chips.append({'label': 'Sex: ' + {'female': 'Female', 'male': 'Male',
                                          'prefer_not_to_say': 'Prefer Not to Say',
                                          'unrecorded': 'Not Recorded'}[sex],
                      'query': _without('sex')})
    if sdg_id:
        chips.append({'label': f'SDG {sdg.number}: {sdg.name}', 'query': _without('sdg_id')})
    if request.args.get('attention'):
        chips.append({'label': 'Attention: ' + evidence['attention_labels'][request.args['attention']],
                      'query': _without('attention')})
    if request.args.get('department', '').strip():
        chips.append({'label': 'Affiliation: ' + request.args['department'].strip(),
                      'query': _without('department')})
    return dict(evidence, active_filter_chips=chips,
        campuses=campuses, selected_campuses=selected, campus_mode=mode,
        campus_error=error, live_query=query, live_navigation_query=dict(query, view=['live']),
        live_scope=scope, live_summary=evidence['evidence_summary'],
        dashboard_data=summarize_report(evidence['evidence_rows']),
        categories=[row[0] for row in db.session.query(Event.category).filter(
            Event.category.isnot(None)).distinct().order_by(Event.category).all()],
        sdgs=sdgs, selected_sex=sex, selected_sdg_id=sdg_id,
        departments=[row[0] for row in departments.distinct().order_by(User.college_affiliation).all()],
        selected_department=request.args.get('department', '').strip())


def _director_calendar(year, month, campus_id=None, category='', dashboard=False):
    now = datetime.now()
    year, month = year or now.year, month or now.month
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        year, month = now.year, now.month
    query = Event.query.options(selectinload(Event.campus), selectinload(Event.sdgs)).filter(
        db.extract('year', Event.date) == year, db.extract('month', Event.date) == month)
    if campus_id:
        query = query.filter(Event.campus_id == campus_id)
    if category:
        query = query.filter(Event.category == category)
    by_day, links = {}, {}
    for event in query.order_by(Event.date, Event.id).all():
        by_day.setdefault(event.date.day, []).append(event)
        links[event.id] = url_for('director.analytics', event_id=event.id,
            start_date=event.date.date().isoformat(), end_date=event.date.date().isoformat(),
            _anchor='decision-records')
    previous = ((year - 1, 12) if month == 1 else (year, month - 1)) if (year, month) != (1, 1) else None
    following = ((year + 1, 1) if month == 12 else (year, month + 1)) if (year, month) != (9999, 12) else None

    def month_url(value):
        if value is None:
            return None
        if dashboard:
            args = request.args.to_dict(flat=False)
            args.update(calendar_year=value[0], calendar_month=value[1], _anchor='activity-calendar')
            return url_for('director.director_dash', **args)
        return url_for('director.activity_calendar', year=value[0], month=value[1],
                       campus_id=campus_id, category=category)

    return dict(calendar_weeks=Calendar(firstweekday=0).monthdayscalendar(year, month),
        calendar_events=by_day, calendar_month=datetime(year, month, 1).strftime('%B %Y'),
        calendar_year=year, calendar_number=month, previous_calendar_url=month_url(previous),
        next_calendar_url=month_url(following), calendar_event_links=links,
        calendar_scope='University Activities', calendar_show_campus=True)


@director_bp.route('/director_dash')
@login_required
@roles_required('director', 'admin')
def director_dash():
    now = datetime.now()
    try:
        period = resolve_period(request.args, now)
    except ReportError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('director.director_dash'))
    evidence = _live_report_context(period)
    counts = Counter(row['campus_id'] for row in evidence['evidence_rows'])
    campuses = [{'id': campus.id, 'name': campus.name, 'activities': counts[campus.id]}
                for campus in evidence['campuses'] if not evidence['campus_error'] and
                (not evidence['selected_campuses'] or
                 ((campus.id in evidence['selected_campuses']) == (evidence['campus_mode'] == 'include')))]
    with_activity = sum(campus['activities'] > 0 for campus in campuses)
    evidence['annual_plan'] = annual_plan_summary(now.year)
    award_years = sorted({row[0] for row in db.session.query(
        db.extract('year', Event.date)).distinct().all()}, reverse=True) or [now.year]
    award_year = request.args.get('award_year', type=int)
    if award_year not in award_years:
        award_year = award_years[0]
    state = {key: request.args.getlist(key) for key in
             ('goal_year', 'sample', 'award_year', 'calendar_year', 'calendar_month') if key in request.args}
    return render_template('director/Director_Dash.html', **evidence,
                           **_director_calendar(request.args.get('calendar_year', type=int),
                                                request.args.get('calendar_month', type=int), dashboard=True),
                           award_years=award_years, award_year=award_year,
                           leaderboards=AnalyticsAggregator.award_leaderboards(award_year),
                           dashboard_state=state,
                           campus_coverage={'campuses': campuses, 'total': len(campuses),
                                            'with_activity': with_activity,
                                            'without_activity': len(campuses) - with_activity}), (400 if evidence['campus_error'] else 200)


@director_bp.route('/director/calendar')
@login_required
@roles_required('director', 'admin')
def activity_calendar():
    campus_id = resolve_campus(request.args.get('campus_id'))
    category = request.args.get('category', '').strip()
    categories = [row[0] for row in db.session.query(Event.category).filter(
        Event.category.isnot(None)).distinct().order_by(Event.category).all()]
    return render_template('director/activity_calendar.html',
                           **_director_calendar(request.args.get('year', type=int),
                                                request.args.get('month', type=int), campus_id, category),
                           campuses=Campus.query.order_by(Campus.name).all(), categories=categories,
                           selected_campus=campus_id, selected_category=category)


@director_bp.route('/analytics')
@login_required
@roles_required('director', 'admin')
def analytics():
    analytics_view = request.args.get('view', 'live').strip().lower()
    if analytics_view not in {'live', 'historical'}:
        analytics_view = 'live'
    try:
        period = resolve_period(request.args)
    except ReportError as exc:
        flash('Use valid report dates, with the start date on or before the end date. ' + str(exc), 'error')
        return redirect(url_for('director.analytics'))
    try:
        parse_date_range(request.args.get('start_date'), request.args.get('end_date'))
    except ReportError:
        flash('Use valid report dates, with the start date on or before the end date.', 'error')
        return redirect(url_for('director.analytics'))
    filters = _historical_filters()
    demographics = AnalyticsAggregator.role_demographics()
    historical_summary = AnalyticsAggregator.historical_summary(**filters)
    historical_campus_data = AnalyticsAggregator.historical_campus_stats(**filters)
    from app.models.event import HistoricalActivity
    activity_types = [row[0] for row in db.session.query(
        HistoricalActivity.activity_type).filter(
            HistoricalActivity.activity_type.isnot(None)).distinct().all()]

    context = _live_report_context(period)
    live_rows, live_summary = context['evidence_rows'], context['live_summary']
    live_start = period['start']
    live_end = period['end']
    live_category = request.args.get('category', '').strip()
    live_sex = context['selected_sex']
    report_page = max(request.args.get('page', 1, type=int), 1)
    report_page_size = 10
    report_total_pages = max(1, (len(live_rows) + report_page_size - 1) // report_page_size)
    report_page = min(report_page, report_total_pages)
    report_rows = live_rows[(report_page - 1) * report_page_size:report_page * report_page_size]
    department = context['selected_department']

    # Supplementary profile evidence retains its independently labelled scope.
    live_campus_filter = resolve_campus(request.args.get('campus_id'))
    top_skills = AnalyticsAggregator.skill_distribution(limit=8)
    top_interests = AnalyticsAggregator.interest_distribution(limit=8)
    department_participants = AnalyticsAggregator.department_participants(
        campus_id=live_campus_filter, department=department or None)
    sex_participation = AnalyticsAggregator.sex_participation(
        start_date=live_start, end_date=live_end,
        category=live_category, sex=live_sex,
        activity_name=request.args.get('activity_name', ''),
        event_ids=[row['event_id'] for row in live_rows])
    historical_query = {'view': 'historical'}
    for key, value in filters.items():
        if value is not None:
            historical_query[key] = value

    selected_year = request.args.get('year', datetime.now().year, type=int)
    annual_plan = annual_plan_summary(selected_year)
    return render_template('director/Director_impact_anlaytics_dash.html',
                            **context,
                            annual_plan=annual_plan,
                            analytics_view=analytics_view,
                            demographics=demographics,
                            historical_summary=historical_summary,
                            historical_campus_data=historical_campus_data,
                            activity_types=activity_types,
                            historical_query=historical_query,
                            selected_filters=filters,
                            live_rows=report_rows,
                            report_page=report_page, report_total_pages=report_total_pages,
                            top_skills=top_skills,
                            top_interests=top_interests,
                            department_participants=department_participants,
                            sex_participation=sex_participation), (400 if context['campus_error'] else 200)


@director_bp.route('/reports/campus.csv')
@login_required
@roles_required('director', 'admin')
def export_campus_csv():
    filters = _historical_filters()
    data = AnalyticsAggregator.historical_campus_stats(**filters)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Campus / Unit', 'Activities', 'Volunteer Participations',
                     'Incomplete Source Rows'])
    for row in data:
        writer.writerow([row['campus'], row['activities'],
                         row['participations'], row['incomplete_records']])
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition':
        'attachment;filename=psu_historical_campus_participation.csv'})


@director_bp.route('/reports/campus.pdf')
@login_required
@roles_required('director', 'admin')
def export_campus_pdf():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, Image)

    filters = _historical_filters()
    data = AnalyticsAggregator.historical_campus_stats(**filters)
    summary = AnalyticsAggregator.historical_summary(**filters)
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4), rightMargin=18 * mm,
        leftMargin=18 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
        title='PSU Historical Campus Participation Report')
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#00408B'),
        fontSize=18, leading=21, alignment=TA_CENTER, spaceAfter=2 * mm)
    subtitle_style = ParagraphStyle(
        'ReportSubtitle', parent=styles['BodyText'], alignment=TA_CENTER,
        textColor=colors.HexColor('#4D596A'), spaceAfter=3 * mm)
    story = []
    logo_path = current_app.static_folder + '/assets/PSU-logo.png'
    story.append(Image(logo_path, width=14 * mm, height=14 * mm))
    story.append(Paragraph('PSU Historical Campus Participation', title_style))
    story.append(Paragraph(
        'Summary of Volunteer Activities, CY 2020–2025 · '
        f'Generated {datetime.now().strftime("%B %d, %Y")}', subtitle_style))
    story.append(Paragraph(
        f'<b>{summary["activities"]}</b> activity records &nbsp;&nbsp;·&nbsp;&nbsp; '
        f'<b>{summary["volunteer_participations"]:,}</b> volunteer participations '
        f'&nbsp;&nbsp;·&nbsp;&nbsp; <b>{summary["incomplete_records"]}</b> incomplete source rows',
        styles['BodyText']))
    story.append(Spacer(1, 3 * mm))
    table_data = [['Campus / Unit', 'Activities', 'Volunteer Participations',
                   'Incomplete Source Rows']]
    table_data.extend([[row['campus'], f"{row['activities']:,}",
                        f"{row['participations']:,}",
                        f"{row['incomplete_records']:,}"] for row in data])
    table = Table(table_data, colWidths=[105 * mm, 37 * mm, 55 * mm, 50 * mm],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00408B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F3F6FC')]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B8C2D1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 3 * mm), Paragraph(
        'Note: Participations are aggregate entries from the source report and '
        'must not be interpreted as unique volunteer accounts. Missing values '
        'were retained rather than estimated.', styles['BodyText'])])
    document.build(story)
    return Response(output.getvalue(), mimetype='application/pdf', headers={
        'Content-Disposition':
        'attachment;filename=psu_historical_campus_participation.pdf'})


# ── Live, event-based university reporting (Director + Admin) ──────────────────

def _report_scope_label(campus_id):
    if campus_id is None:
        return 'All Campuses'
    campus = db.session.get(Campus, campus_id)
    return f'{campus.name} Campus' if campus else 'All Campuses'


def _university_report_payload():
    """Build the filtered dataset for the live university report.

    Returns (rows, summary, meta, error). Authorization: directors and admins
    may request any single campus or all campuses; the campus is validated and
    never trusted blindly. Invalid dates raise ReportError -> caller redirects.
    """
    campuses = Campus.query.order_by(db.func.lower(Campus.name), Campus.name, Campus.id).all()
    selected, mode, allowed, error = _live_campuses(campuses)
    if error:
        abort(400, description=error)
    export_period = resolve_period(dict(request.args, period=request.args.get('period', 'all')))
    start, end = export_period['start'], export_period['end']
    category = request.args.get('category', '').strip()
    sex = request.args.get('sex', '').strip().lower()
    sdg_id = request.args.get('sdg_id', type=int)
    sdg = db.session.get(SdgGoal, sdg_id) if sdg_id else None
    rows, summary = build_events_report(
        campus_ids=allowed, start_date=start, end_date=end,
        category=category, sex=sex if sex in (
            'male', 'female', 'prefer_not_to_say', 'unrecorded') else None,
        sdg_id=sdg.id if sdg else None,
        activity_name=request.args.get('activity_name', ''),
        attention=request.args.get('attention', ''), event_id=request.args.get('event_id'))
    names = [campus.name for campus in campuses if campus.id in selected]
    scope = ('All Campuses' if not selected else
             ('All campuses except: ' if mode == 'exclude' else 'Selected campuses: ') + ', '.join(names))
    role_label = 'Administration' if current_user.role == 'admin' else 'Director'
    meta = _build_meta(
        title='University-wide Activity Report', scope=scope,
        start_date=start, end_date=end, category=category,
        role_label=role_label)
    meta['activity_name'] = request.args.get('activity_name', '').strip()
    if sex in ('male', 'female', 'prefer_not_to_say', 'unrecorded'):
        meta['scope'] += ' / Sex response: ' + sex.replace('_', ' ') + ' / Target achievement unavailable for a participant subset'
    if request.args.get('attention'):
        from app.dashboard import ATTENTION_LABELS
        meta['scope'] += ' / ' + ATTENTION_LABELS[request.args['attention']]
    return rows, summary, meta


@director_bp.route('/reports/university.csv')
@login_required
@roles_required('director', 'admin')
def export_university_csv():
    try:
        rows, summary, meta = _university_report_payload()
    except ReportError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('director.analytics'))
    csv_data = render_csv(rows, summary, meta)
    return Response(csv_data, mimetype='text/csv', headers={
        'Content-Disposition':
        'attachment;filename=psu_university_activity.csv'})


@director_bp.route('/reports/university.pdf')
@login_required
@roles_required('director', 'admin')
def export_university_pdf():
    try:
        rows, summary, meta = _university_report_payload()
    except ReportError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('director.analytics'))
    pdf_data = render_pdf(rows, summary, meta)
    return Response(pdf_data, mimetype='application/pdf', headers={
        'Content-Disposition':
        'attachment;filename=psu_university_activity.pdf'})
