"""
Shared Reporting Utilities for PSU Volunteer Hub
================================================
Centralizes filtered event/participation reporting so the *same* dataset
feeds HTML views, CSV exports, and PDF exports. This guarantees that the
filters a user applies in the UI produce identical CSV and PDF output.

All authorization/scoping decisions happen in the calling route:
- Coordinators always pass their own campus_id (never a client value).
- Directors/Admins may pass an optional campus_id (validated) or None
  for university-wide reporting.
"""
from datetime import datetime, timedelta
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload, selectinload, load_only

from app.models import db
from app.models.event import Event, Registration, Attendance, Campus, SdgGoal
from app.models.user import User


class ReportError(ValueError):
    """Raised for invalid user-supplied report parameters (bad dates, etc.)."""


def _date_range_label(start_date, end_date):
    start = (start_date or '').strip()
    end = (end_date or '').strip()
    if start and end:
        return f'{start} to {end}'
    if start:
        return f'From {start}'
    if end:
        return f'Until {end}'
    return 'All dates'


def parse_date_range(start_date, end_date):
    """Return (start, end) datetimes or None for empty values.

    The end boundary is made inclusive of the whole end day so a report for
    "2025-08-31" includes events on that date. Raises ReportError on malformed
    input or when start_date is after end_date.
    """
    start = None
    end = None
    if start_date:
        try:
            start = datetime.strptime(start_date.strip(), '%Y-%m-%d')
        except (ValueError, AttributeError):
            raise ReportError('start_date must be in YYYY-MM-DD format')
    if end_date:
        try:
            end = datetime.strptime(end_date.strip(), '%Y-%m-%d')
        except (ValueError, AttributeError):
            raise ReportError('end_date must be in YYYY-MM-DD format')
    if start and end and start > end:
        raise ReportError('start_date must be on or before end_date')
    return start, end


def resolve_campus(campus_id, allow_all=True):
    """Validate a client-supplied campus id.

    Returns the integer campus id, or None when the value means "all"
    (empty string, the literal 'all', or an unknown id when allow_all).
    Raises ReportError only when allow_all is False and the id is invalid.
    """
    if campus_id in (None, '', 'all'):
        return None
    try:
        cid = int(campus_id)
    except (TypeError, ValueError):
        return None if allow_all else report_invalid()
    from app.campuses import official_campus
    if official_campus(cid) is None:
        return None if allow_all else report_invalid()
    return cid


def report_invalid():
    raise ReportError('invalid campus_id')


def build_events_report(campus_id=None, start_date=None, end_date=None,
                        category=None, sex=None, sdg_id=None, activity_name=None,
                        campus_ids=None, attention=None, now=None, event_id=None, event_ids=None,
                        include_sdgs=True, limit=None, offset=0, include_summary=True):
    """Return (rows, summary) for the filtered event dataset.

    campus_id=None means all campuses. Coordinators must pass their own
    campus id; this function never derives a scope from the request.
    campus_ids adds an intersecting allow-list: None is unrestricted, [] is
    empty, and a None entry includes activities without an assigned campus.
    """
    from app.dashboard import ATTENTION_LABELS
    start, end = parse_date_range(start_date, end_date)
    now = now or datetime.now()
    if attention and attention not in ATTENTION_LABELS:
        raise ReportError('Choose a valid attention filter.')
    if attention == 'missed_targets' and sex:
        raise ReportError('Clear the sex filter to review whole-activity participant targets.')

    query = Event.query
    if event_ids is not None:
        query = query.filter(Event.id.in_(event_ids))
    if event_id is not None:
        try:
            event_id = int(event_id)
            if event_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ReportError('Choose a valid activity record.')
        query = query.filter(Event.id == event_id)
    if campus_id:
        query = query.filter(Event.campus_id == campus_id)
    if campus_ids is not None:
        query = query.filter(Event.campus_id.in_(campus_ids) |
                             (Event.campus_id.is_(None) if None in campus_ids else db.false()))
    if start:
        query = query.filter(Event.date >= start)
    if end:
        query = query.filter(Event.date < end + timedelta(days=1))
    if category:
        query = query.filter(Event.category == category)
    if activity_name and activity_name.strip():
        query = query.filter(Event.title.icontains(activity_name.strip(), autoescape=True))
    if sdg_id:
        query = query.filter(Event.sdgs.any(SdgGoal.id == sdg_id))

    event_ids = query.with_entities(Event.id).statement
    sex_scope = db.true()
    if sex in ('male', 'female', 'prefer_not_to_say'):
        sex_scope = User.sex == sex
    elif sex == 'unrecorded':
        sex_scope = User.id.isnot(None) & User.sex.is_(None)
    eligible = Registration.status != 'cancelled'
    valid = eligible & sex_scope
    attendance_eligible = eligible | Registration.status.is_(None)

    def count_when(condition):
        return func.count(case((condition, 1)))

    registration_counts = db.session.query(
            Registration.event_id,
            count_when(valid).label('registrations'),
            count_when(valid & Registration.user_id.isnot(None)).label('psu'),
            count_when(valid & Registration.external_participant_id.isnot(None)).label('external'),
            count_when((Registration.status == 'completed') & sex_scope).label('completed'),
            count_when(Registration.status == 'cancelled').label('cancelled'),
            count_when(attendance_eligible & Attendance.id.is_(None)).label('missing'),
            count_when(attendance_eligible & (Attendance.status == 'present') &
                       ((Registration.status != 'completed') | Registration.status.is_(None))).label('unconfirmed'),
            count_when(valid & (Attendance.status == 'present')).label('outcome'),
            count_when(valid & (Attendance.status == 'present') & (Registration.status == 'completed')).label('verified_completed'),
        ).outerjoin(User, Registration.user_id == User.id).outerjoin(
            Attendance, Attendance.registration_id == Registration.id).filter(
            Registration.event_id.in_(event_ids)).group_by(Registration.event_id).subquery()
    attendance_counts = db.session.query(
        Attendance.event_id, func.count(Attendance.id).label('attended')).outerjoin(
        User, Attendance.user_id == User.id).filter(
        Attendance.event_id.in_(event_ids), Attendance.status == 'present',
        sex_scope).group_by(Attendance.event_id).subquery()
    columns = [func.coalesce(column, 0) for column in list(registration_counts.c)[1:]]
    data_query = query.outerjoin(registration_counts, registration_counts.c.event_id == Event.id).outerjoin(
        attendance_counts, attendance_counts.c.event_id == Event.id)
    sql_ended = func.coalesce(Event.end_date, Event.date) <= now
    sql_complete = sql_ended & (columns[5] == 0) & (columns[6] == 0)
    if attention == 'pending_attendance':
        data_query = data_query.filter(sql_ended & ~sql_complete)
    elif attention == 'low_attendance':
        data_query = data_query.filter(sql_complete, columns[0] > 0, columns[7] * 4 < columns[0] * 3)
    elif attention == 'missed_targets':
        data_query = data_query.filter(sql_complete, Event.target_participants > 0,
                                       columns[7] < Event.target_participants)
    events_query = data_query.add_columns(
        *columns, func.coalesce(attendance_counts.c.attended, 0)).options(
        load_only(Event.title, Event.date, Event.end_date, Event.campus_id, Event.category, Event.target_participants),
        joinedload(Event.campus)
    ).order_by(Event.date.desc(), Event.id.desc())
    if include_sdgs:
        events_query = events_query.options(selectinload(Event.sdgs).load_only(SdgGoal.number))
    if limit is not None:
        events_query = events_query.offset(max(0, offset)).limit(limit + (1 if include_summary and not offset else 0))
    events = events_query.all()
    complete_scope = limit is None or (not offset and len(events) <= limit)
    if limit is not None:
        events = events[:limit]

    rows = []
    total_reg = 0
    total_attended = 0
    total_completed = 0
    total_psu = 0
    total_external = 0
    total_cancelled = 0
    total_target = 0

    for e, reg, psu, external, completed, cancelled, missing, unconfirmed, outcome_attended, verified_completed, attended in events:
        target = e.target_participants
        ended = now >= (e.end_date or e.date)
        complete = ended and not missing and not unconfirmed
        if attention == 'pending_attendance' and not (ended and not complete):
            continue
        if attention == 'low_attendance' and not (complete and reg and outcome_attended / reg < .75):
            continue
        if attention == 'missed_targets' and not (complete and target and target > 0 and outcome_attended < target):
            continue
        campus_name = e.campus.name if e.campus else ''
        rows.append({
            'event_id': e.id,
            'campus_id': e.campus_id,
            'end_date': e.end_date or e.date,
            'ended': ended,
            'attendance_complete': complete,
            'missing_attendance': missing,
            'unconfirmed_present': unconfirmed,
            'outcome_attended': outcome_attended,
            'title': e.title,
            'date': e.date,
            'campus': campus_name,
            'category': e.category or 'General',
            'sdgs': (', '.join(f'SDG {goal.number}' for goal in e.sdgs) or 'Not tagged') if include_sdgs else 'Not tagged',
            'registrations': reg,
            'psu_registrations': psu,
            'external_registrations': external,
            'attended': attended,
            'completed': completed,
            'verified_completed': verified_completed,
            'cancelled': cancelled,
            'target_participants': target,
            'completion_percentage': round(outcome_attended / target * 100, 1)
                                     if target and target > 0 and complete and not sex else None,
        })
        total_reg += reg
        total_psu += psu
        total_external += external
        total_attended += attended
        total_completed += completed
        total_cancelled += cancelled
        total_target += target or 0

    summary = {
        'event_count': len(rows),
        'total_registrations': total_reg,
        'total_psu': total_psu,
        'total_external': total_external,
        'total_attended': total_attended,
        'total_completed': total_completed,
        'total_cancelled': total_cancelled,
        'total_target_participants': total_target,
    }
    if include_summary and not complete_scope:
        totals = data_query.with_entities(func.count(Event.id), *[
            func.coalesce(func.sum(column), 0) for column in
            (columns[0], columns[1], columns[2], func.coalesce(attendance_counts.c.attended, 0),
             columns[3], columns[4], func.coalesce(Event.target_participants, 0))]).one()
        summary = dict(zip(('event_count', 'total_registrations', 'total_psu', 'total_external',
                            'total_attended', 'total_completed', 'total_cancelled', 'total_target_participants'), totals))
    return rows, summary


def batched_events_report(**scope):
    """Return a full-scope summary and an iterator that fetches 1,000 detail rows at a time."""
    batch, summary = build_events_report(**scope, limit=1000)
    def records():
        current, offset = batch, 0
        while current:
            yield from current
            if offset + len(current) >= summary['event_count']:
                break
            offset += 1000
            current, _ = build_events_report(**scope, limit=1000, offset=offset, include_summary=False)
    return records(), summary


def _build_meta(title, scope, start_date, end_date, category,
                role_label=None, historical_note=None):
    return {
        'title': title,
        'scope': scope,
        'date_range': _date_range_label(start_date, end_date),
        'category': (category or 'All Categories'),
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'role_label': role_label or '',
        'historical_note': historical_note,
    }


def csv_safe(value):
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r', '\n'):
        return "'" + value
    return value


def render_csv(rows, summary, meta):
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f"PSU Volunteer Hub - {meta['title']}"])
    writer.writerow([f"Scope: {meta['scope']}"])
    writer.writerow([f"Date range: {meta['date_range']}"])
    writer.writerow([f"Category: {meta['category']}"])
    if meta.get('activity_name'):
        writer.writerow([f"Activity name contains: {meta['activity_name']}"])
    writer.writerow([f"Generated: {meta['generated']}"])
    writer.writerow([])
    writer.writerow(['Activity', 'Date', 'Campus', 'Category', 'SDGs',
                     'Registrations', 'PSU', 'External', 'Actual Participants',
                     'Cancelled', 'Completed', 'Target Participants', 'Target Completion'])
    for r in rows:
        writer.writerow([
            csv_safe(r['title']), r['date'].strftime('%Y-%m-%d'), csv_safe(r['campus']),
            csv_safe(r['category']), csv_safe(r['sdgs']), r['registrations'], r['psu_registrations'],
            r['external_registrations'], r['attended'], r['cancelled'],
            r['completed'], r['target_participants'] or '',
            f"{r['completion_percentage']}%" if r['completion_percentage'] is not None else '',
        ])
    writer.writerow([])
    writer.writerow(['TOTAL', '', '', '', '', summary['total_registrations'],
                     summary['total_psu'], summary['total_external'],
                     summary['total_attended'], summary['total_cancelled'],
                     summary['total_completed'], summary['total_target_participants'], ''])
    return output.getvalue()


def render_pdf(rows, summary, meta):
    import io
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    output = io.BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=meta['title'])
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Title'],
        textColor=colors.HexColor('#00408B'), fontSize=16, leading=19)
    small = styles['BodyText']

    story = []
    story.append(Paragraph(
        f"PSU Volunteer Hub &middot; {escape(meta['title'])}", title_style))
    role_line = f" ({escape(meta['role_label'])})" if meta.get('role_label') else ''
    story.append(Paragraph(
        f"Report scope{role_line}: {escape(meta['scope'])}<br/>"
        f"Date range: {meta['date_range']}<br/>"
        f"Category: {escape(meta['category'])}<br/>"
        f"Generated: {meta['generated']}", small))
    story.append(Spacer(1, 4 * mm))
    if meta.get('activity_name'):
        story.append(Paragraph(
            f"Activity name contains: {escape(meta['activity_name'])}", small))
        story.append(Spacer(1, 4 * mm))

    data = [['Activity', 'Date', 'Campus', 'Category', 'SDGs', 'Reg.', 'PSU', 'Ext.',
             'Actual', 'Cancelled', 'Completed', 'Target', 'Progress']]
    for r in rows:
        data.append([
            r['title'], r['date'].strftime('%Y-%m-%d'), r['campus'],
            r['category'], r['sdgs'], str(r['registrations']), str(r['psu_registrations']),
            str(r['external_registrations']), str(r['attended']),
            str(r['cancelled']), str(r['completed']),
            str(r['target_participants'] or ''),
            f"{r['completion_percentage']}%" if r['completion_percentage'] is not None else '',
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00408B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B8C2D1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (5, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F3F6FC')]),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"<b>Summary</b> &mdash; Events: {summary['event_count']} &middot; "
        f"Registrations: {summary['total_registrations']} "
        f"(PSU: {summary['total_psu']}, External: {summary['total_external']}) &middot; "
        f"Verified actual participants: {summary['total_attended']} &middot; "
        f"Cancelled: {summary['total_cancelled']} &middot; "
        f"Completed: {summary['total_completed']}", small))
    if meta.get('historical_note'):
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(escape(meta['historical_note']), small))
    document.build(story)
    return output.getvalue()
