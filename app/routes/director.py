"""
Director Routes for PSU Volunteer Hub
========================================
Manages director dashboard and analytics views.
Uses AnalyticsAggregator for all aggregation queries.
"""
import csv
import io
from calendar import Calendar
from datetime import datetime
from flask import Blueprint, render_template, Response, current_app, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app.utils.decorators import roles_required
from app.recommendation.analytics import AnalyticsAggregator
from app.models import db
from app.models.event import Event, Campus, SdgGoal
from app.models.user import User
from app.dashboard import summarize_report, resolve_period, dashboard_evidence, consolidate_attention
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
    evidence = dashboard_evidence({}, period, now)
    pending, _ = build_events_report(attention='pending_attendance', now=now)
    pending.sort(key=lambda row: (row['end_date'], row['event_id']))
    evidence['attention_items'] = consolidate_attention(evidence['performance'], pending)
    active = {row['campus_id'] for row in evidence['evidence_rows']}
    return render_template('director/Director_Dash.html', **evidence,
                           inactive_campuses=[campus for campus in Campus.query.order_by(Campus.name).all()
                                              if campus.id not in active],
                           dashboard_data=summarize_report(evidence['evidence_rows']))


@director_bp.route('/director/calendar')
@login_required
@roles_required('director', 'admin')
def activity_calendar():
    now = datetime.now()
    year = request.args.get('year', now.year, type=int) or now.year
    month = request.args.get('month', now.month, type=int) or now.month
    campus_id = resolve_campus(request.args.get('campus_id'))
    category = request.args.get('category', '').strip()
    if not 1 <= month <= 12:
        year, month = now.year, now.month
    query = Event.query.filter(db.extract('year', Event.date) == year,
                               db.extract('month', Event.date) == month)
    if campus_id:
        query = query.filter(Event.campus_id == campus_id)
    if category:
        query = query.filter(Event.category == category)
    by_day = {}
    for event in query.order_by(Event.date).all():
        by_day.setdefault(event.date.day, []).append(event)
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    following = (year + 1, 1) if month == 12 else (year, month + 1)
    categories = [row[0] for row in db.session.query(Event.category).filter(
        Event.category.isnot(None)).distinct().order_by(Event.category).all()]
    return render_template('director/activity_calendar.html',
                           calendar_weeks=Calendar(firstweekday=0).monthdayscalendar(year, month),
                           calendar_events=by_day, calendar_month=datetime(year, month, 1).strftime('%B %Y'),
                           calendar_year=year, calendar_number=month,
                           previous_calendar=previous, next_calendar=following,
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
    campuses = Campus.query.order_by(db.func.lower(Campus.name), Campus.name, Campus.id).all()
    activity_types = [row[0] for row in db.session.query(
        HistoricalActivity.activity_type).filter(
            HistoricalActivity.activity_type.isnot(None)).distinct().all()]

    # Live event-based report (date / campus / category filters)
    selected_campuses, campus_mode, live_campus_ids, campus_error = _live_campuses(campuses)
    live_start = period['start']
    live_end = period['end']
    live_category = request.args.get('category', '').strip()
    live_sex = request.args.get('sex', '').strip().lower()
    live_sex = live_sex if live_sex in (
        'male', 'female', 'prefer_not_to_say', 'unrecorded') else None
    live_sdg_id = request.args.get('sdg_id', type=int)
    if live_sdg_id and db.session.get(SdgGoal, live_sdg_id) is None:
        live_sdg_id = None
    try:
        evidence = dashboard_evidence(dict(campus_ids=live_campus_ids,
            category=live_category, sex=live_sex, sdg_id=live_sdg_id,
            activity_name=request.args.get('activity_name', ''),
            attention=request.args.get('attention', ''), event_id=request.args.get('event_id')), period)
        live_rows, live_summary = evidence['evidence_rows'], evidence['evidence_summary']
    except ReportError:
        abort(400, description='Choose valid report dates and attention filters. Clear the sex filter to review participant targets.')
    dashboard_data = summarize_report(live_rows)
    report_page = max(request.args.get('page', 1, type=int), 1)
    report_page_size = 10
    report_total_pages = max(1, (len(live_rows) + report_page_size - 1) // report_page_size)
    report_page = min(report_page, report_total_pages)
    report_rows = live_rows[(report_page - 1) * report_page_size:report_page * report_page_size]
    categories = [row[0] for row in db.session.query(Event.category).filter(
        Event.category.isnot(None)).distinct().order_by(Event.category).all()]
    department = request.args.get('department', '').strip()
    selected_campus_id = request.args.get('campus_id', type=int)
    department_query = db.session.query(User.college_affiliation).filter(
        User.college_affiliation.isnot(None))
    if selected_campus_id:
        department_query = department_query.filter(User.campus_id == selected_campus_id)
    departments = [row[0] for row in department_query.distinct().order_by(
        User.college_affiliation).all()]

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
    award_years = sorted({event.date.year for event in Event.query.with_entities(Event.date).all()}, reverse=True)
    award_year = request.args.get('award_year', type=int)
    if award_year not in award_years:
        award_year = award_years[0] if award_years else datetime.now().year
    leaderboards = (AnalyticsAggregator.award_leaderboards(award_year)
                    if current_user.role == 'director' else None)

    query = request.args.to_dict(flat=False)
    live_query = {
        key: values for key, values in query.items()
        if key not in {'view', 'page', 'start_year', 'end_year', 'activity_type'}
    }
    live_query.update(start_date=[live_start], end_date=[live_end])
    if not campus_error:
        live_query['campus'] = [str(campus_id) for campus_id in selected_campuses]
        live_query['campus_mode'] = [campus_mode]
    historical_query = {'view': 'historical'}
    for key, value in filters.items():
        if value is not None:
            historical_query[key] = value

    return render_template('director/Director_impact_anlaytics_dash.html',
                            **evidence,
                            analytics_view=analytics_view,
                            demographics=demographics,
                            historical_summary=historical_summary,
                            historical_campus_data=historical_campus_data,
                            campuses=campuses, activity_types=activity_types,
                            selected_campuses=selected_campuses, campus_mode=campus_mode,
                            campus_error=campus_error,
                            live_query=live_query,
                            live_navigation_query=dict(live_query, view=['live']),
                            historical_query=historical_query,
                            categories=categories,
                            sdgs=SdgGoal.query.order_by(SdgGoal.number).all(),
                            selected_sex=live_sex, selected_sdg_id=live_sdg_id,
                            selected_filters=filters,
                            live_rows=report_rows, live_summary=live_summary,
                            dashboard_data=dashboard_data,
                            report_page=report_page, report_total_pages=report_total_pages,
                            top_skills=top_skills,
                            top_interests=top_interests,
                            departments=departments, selected_department=department,
                            department_participants=department_participants,
                            sex_participation=sex_participation,
                            award_years=award_years, award_year=award_year,
                            leaderboards=leaderboards), (400 if campus_error else 200)


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
