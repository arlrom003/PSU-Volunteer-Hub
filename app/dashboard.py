"""Presentation summaries derived from the same rows as PDF and CSV reports."""

from calendar import monthrange
from datetime import datetime, timedelta


ATTENTION_LABELS = {
    'pending_attendance': 'Attendance Awaiting Completion',
    'low_attendance': 'Attendance below the 75% Review Guide',
    'missed_targets': 'Participant Targets Not Reached',
}

GUIDANCE_SCOPE_KEYS = ('period', 'start_date', 'end_date', 'campus', 'campus_mode',
                       'campus_id', 'category', 'sex', 'sdg_id', 'activity_name',
                       'attention', 'event_id', 'department')
GUIDANCE_TEXT = {
    'pending_attendance': (1, 'Complete outstanding attendance records so verified results can be assessed.'),
    'missed_targets': (3, 'Review the activity target and plan additional participant outreach.'),
    'low_attendance': (4, 'Review reminders, participant confirmation, and outreach timing.'),
    'no_activities': (5, 'Plan or publish a campus activity for the selected period.'),
}


def operational_guidance(rows, scope_label, show_targets=True, allow_scheduling=False):
    """Turn report findings into follow-up advice with supporting counts.

    Prioritize missing attendance, missed targets, then rates below 75%.
    Judge rates/targets only after attendance is complete. An empty report
    suggests scheduling only when caller allows it; advice changes no records.
    """
    performance = performance_summary(rows, show_targets)
    result = []
    for code, key in [('pending_attendance', 'pending'), ('missed_targets', 'missed'),
                      ('low_attendance', 'low')]:
        affected = performance[key]
        if not affected:
            continue
        priority, text = GUIDANCE_TEXT[code]
        if key == 'pending':
            evidence = (f'{len(affected)} activities; '
                        f'{sum(row["missing_attendance"] for row in affected)} missing attendance records; '
                        f'{sum(row["unconfirmed_present"] for row in affected)} awaiting completion confirmation.')
        elif key == 'missed':
            evidence = (f'{len(affected)} activities; {sum(row["outcome_attended"] for row in affected)} '
                        f'attended / {sum(row["target_participants"] for row in affected)} participant target.')
        else:
            evidence = (f'{len(affected)} activities below the 75% review guide; '
                        f'{sum(row["outcome_attended"] for row in affected)} attended / '
                        f'{sum(row["registrations"] for row in affected)} registrations in those activities.')
        result.append(dict(code=code, priority=priority, text=text, evidence=evidence,
                           scope_label=scope_label, event_id=affected[0]['event_id'] if len(affected) == 1 else None))
    if not rows and allow_scheduling:
        priority, text = GUIDANCE_TEXT['no_activities']
        result.append(dict(code='no_activities', priority=priority, text=text,
                           evidence='0 campus activity records.', scope_label=scope_label, event_id=None))
    return result


def scheduling_scope(query):
    """Allow scheduling advice only without narrow activity/participant filters.

    Zero filtered matches do not prove campus has no scheduled activities.
    """
    return not any(query.get(key) for key in
                   ('category', 'sex', 'sdg_id', 'activity_name', 'attention', 'event_id', 'department', 'status'))


def guidance_scope_label(period, query):
    """Label advice with report dates and supplied category/name/sex/SDG scope."""
    parts = [period['label']]
    for key, label in [('category', 'Category'), ('activity_name', 'Activity'), ('sex', 'Sex'), ('sdg_id', 'SDG')]:
        if query.get(key):
            parts.append(f'{label}: {query.get(key)}')
    return '; '.join(parts)


def present_guidance(records, campus_id, goal_year, query=None):
    """Attach internal action links to the three highest-priority findings.

    Preserve allowed report filters and force the finding's campus scope.
    Directors review reports/goals; other callers can reach attendance or
    activity creation. Return copies so source findings remain reusable.
    """
    from flask import url_for
    from flask_login import current_user
    director = current_user.role == 'director'
    query = query or {}
    scope = {key: value for key, value in query.items() if key in GUIDANCE_SCOPE_KEYS}
    scope.update(campus=[str(campus_id)], campus_mode=['include'])
    scope.pop('campus_id', None)
    result = []
    for record in sorted(records, key=lambda item: item['priority'])[:3]:
        item = dict(record, campus_id=campus_id, goal_year=goal_year, scope_query=scope)
        code = item['code']
        if code in ('no_targets', 'remaining_goals'):
            item['action_label'] = 'Review Goal Proposals' if code == 'no_targets' else 'View Campus Goals'
            item['url'] = (url_for('goals.workspace') if code == 'no_targets' else
                           url_for('goals.details', year=goal_year, campus=campus_id))
        elif code == 'no_activities' and not director:
            item.update(action_label='Create Activity', url=url_for('coordinator.create_activity'))
        elif code == 'pending_attendance' and not director:
            item.update(action_label='Complete Attendance',
                        url=url_for('coordinator.attendance', event_id=item['event_id']))
        else:
            target = dict(scope, attention=code if code in ATTENTION_LABELS else '', page=1)
            if item['event_id']:
                target['event_id'] = item['event_id']
            item['action_label'] = 'View Campus Report' if code == 'no_activities' else 'Review Activities'
            item['url'] = url_for('director.analytics' if director else 'coordinator.analytics', **target) + '#decision-records'
        result.append(item)
    return result


def resolve_period(args, now=None):
    """Resolve reporting dates; explicit start/end parameters override presets.

    Default is this month through today. Compare that preset with the same
    elapsed days last month, capped at last month's length. Last-month, all,
    and custom ranges have no automatic comparison. Reject invalid periods,
    malformed dates, and reversed ranges through shared report validation.
    """
    from app.reports import parse_date_range, ReportError
    now = now or datetime.now()
    today = now.date()
    first = today.replace(day=1)
    previous_end = first - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    period = args.get('period', 'this_month')
    if period not in ('this_month', 'last_month', 'all', 'custom'):
        raise ReportError('Choose a valid reporting period.')
    comparison = None
    if 'start_date' in args or 'end_date' in args or period == 'custom':
        start, end = args.get('start_date', '').strip(), args.get('end_date', '').strip()
        parse_date_range(start, end)
        period = 'custom' if start or end else 'all'
    elif period == 'all':
        start, end = '', ''
    elif period == 'last_month':
        start, end = previous_start.isoformat(), previous_end.isoformat()
    else:
        start, end = first.isoformat(), today.isoformat()
        comparison = (previous_start.isoformat(), previous_end.replace(
            day=min(today.day, monthrange(previous_end.year, previous_end.month)[1])).isoformat())
    label = f'{start} to {end}' if start and end else (
        f'From {start}' if start else f'Until {end}' if end else 'All Dates')
    return {'value': period, 'start': start, 'end': end, 'label': label,
            'comparison': comparison}


def performance_summary(rows, show_targets=True):
    """Compute screen totals and final outcomes from existing report rows.

    Activity/registration/present totals include provisional rows. Overall
    attendance rate uses only complete rows: summed outcome attendance /
    summed registrations * 100, not an average of event percentages.
    No eligible registrations means rate None. Positive targets on complete
    rows can be assessed; hiding targets suppresses their count/missed list.
    Pending means ended but incomplete; low attendance means strictly <75%.
    """
    complete = [row for row in rows if row['attendance_complete']]
    registrations = sum(row['registrations'] for row in complete)
    attended = sum(row['outcome_attended'] for row in complete)
    targets = [row for row in complete if (row['target_participants'] or 0) > 0]
    return {
        'activities': len(rows),
        'registrations': sum(row['registrations'] for row in rows),
        'attended': sum(row['attended'] for row in rows),
        'rate': round(attended / registrations * 100, 1) if registrations else None,
        'rate_registrations': registrations,
        'rate_attended': attended,
        'targets_met': sum(row['outcome_attended'] >= row['target_participants'] for row in targets),
        'targets_count': len(targets) if show_targets else 0,
        'show_targets': show_targets,
        'pending': [row for row in rows if row['ended'] and not row['attendance_complete']],
        'low': [row for row in complete if row['registrations'] and
                row['outcome_attended'] / row['registrations'] < .75],
        'missed': [row for row in targets if row['outcome_attended'] < row['target_participants']]
                  if show_targets else [],
    }


def dashboard_evidence(scope, period, now=None):
    """Build dashboard evidence from the same filtered rows used by exports.

    Reuse performance rules for findings and charts. Hide whole-event target
    assessment under a sex filter. When a comparison period exists, subtract
    previous values from current values; rate deltas are percentage points.
    Attention-filtered reports skip deltas. Coordinator scheduling advice
    appears only for an empty, suitably broad campus report.
    """
    from app.reports import build_events_report
    now = now or datetime.now()
    rows, summary = build_events_report(**scope, start_date=period['start'],
                                       end_date=period['end'], now=now)
    performance = performance_summary(rows, show_targets=not scope.get('sex'))
    deltas = {}
    if period['comparison'] and not scope.get('attention'):
        previous, _ = build_events_report(**scope, start_date=period['comparison'][0],
                                          end_date=period['comparison'][1], now=now)
        baseline = performance_summary(previous, show_targets=not scope.get('sex'))
        for key in ('activities', 'registrations', 'attended', 'rate'):
            if performance[key] is not None and baseline[key] is not None:
                deltas[key] = round(performance[key] - baseline[key], 1)
    items = consolidate_attention(performance)
    for item in items:
        item['guidance'] = operational_guidance([item], guidance_scope_label(period, scope), not scope.get('sex'))
    performance_guidance = []
    if scope.get('campus_id'):
        from flask import has_request_context, request
        from flask_login import current_user
        if has_request_context() and current_user.is_authenticated and current_user.role == 'coordinator':
            records = operational_guidance(rows, period['label'], not scope.get('sex'), scheduling_scope(scope))
            performance_guidance = present_guidance([item for item in records if item['code'] == 'no_activities'],
                scope['campus_id'], request.args.get('goal_year'), request.args.to_dict(flat=False))
    return dict(evidence_rows=rows, evidence_summary=summary, performance=performance,
                period=period, deltas=deltas, attention_labels=ATTENTION_LABELS,
                attention_items=items, performance_guidance=performance_guidance)


def consolidate_attention(performance, pending=None):
    """Merge pending, missed-target, and low-rate findings by event ID.

    Keep every reason on one activity row instead of showing duplicates.
    An explicit pending list can supply an all-date backlog while other
    findings retain the selected report period. Copy rows before annotating.
    """
    items = {}
    groups = [('pending', performance['pending'] if pending is None else pending),
              ('missed', performance['missed']), ('low', performance['low'])]
    for kind, rows in groups:
        for row in rows:
            item = items.setdefault(row['event_id'], dict(row, reasons=[], is_pending=False))
            item.setdefault('guidance', [])
            code = {'pending': 'pending_attendance', 'missed': 'missed_targets', 'low': 'low_attendance'}[kind]
            priority, text = GUIDANCE_TEXT[code]
            item['guidance'].append(dict(code=code, priority=priority, text=text))
            if kind == 'pending':
                item['is_pending'] = True
                if row['missing_attendance']:
                    count = row['missing_attendance']
                    item['reasons'].append(f"{count} missing attendance {'record' if count == 1 else 'records'}")
                if row['unconfirmed_present']:
                    item['reasons'].append(f"{row['unconfirmed_present']} awaiting completion confirmation")
            elif kind == 'missed':
                item['reasons'].append(f"{row['outcome_attended']} attended / {row['target_participants']} target")
            else:
                rate = round(row['outcome_attended'] / row['registrations'] * 100, 1)
                item['reasons'].append(f'{rate}% attendance, below the 75% review guide')
    return list(items.values())


def summarize_report(rows):
    """Group report rows into campus/category charts and monthly/weekly trends.

    Use event start dates, not signup dates, for time buckets. Keep all present
    counts separate from complete-attendance outcome counts. Each activity
    counts once per listed SDG, so SDG totals need not equal activity count;
    untagged rows retain their 'Not tagged' bucket. No new database queries.
    Return the ten activities with most registrations for the performance list.
    """
    campuses, categories, months, weeks, sdgs = {}, {}, {}, {}, {}
    for row in rows:
        for groups, key in (
            (campuses, row['campus'] or 'Unassigned'),
            (categories, row['category']),
            (months, row['date'].strftime('%Y-%m')),
            (weeks, row['date'].strftime('%G-W%V')),
        ):
            counts = groups.setdefault(key, {'registrations': 0, 'attended': 0,
                                             'final_registrations': 0, 'final_attended': 0})
            counts['registrations'] += row['registrations']
            counts['attended'] += row['attended']
            if row.get('attendance_complete'):
                counts['final_registrations'] += row['registrations']
                counts['final_attended'] += row['outcome_attended']
        for goal in row['sdgs'].split(', '):
            sdgs[goal] = sdgs.get(goal, 0) + 1

    def comparison(groups):
        """Sort by registrations, then label; keep final and provisional rates separate."""
        return [
            {'label': label, **counts,
             'final_rate': round(counts['final_attended'] / counts['final_registrations'] * 100, 1)
             if counts['final_registrations'] else None,
             'rate': round(counts['attended'] / counts['registrations'] * 100, 1)
             if counts['registrations'] else 0}
            for label, counts in sorted(
                groups.items(), key=lambda item: (-item[1]['registrations'], item[0]))
        ]

    def trend(groups):
        """Sort year-month/ISO-week keys chronologically; leave absent periods unfilled."""
        periods = sorted(groups)
        return {
            'labels': periods,
            'primary': [groups[period]['registrations'] for period in periods],
            'secondary': [groups[period]['attended'] for period in periods],
            'primaryName': 'Registrations', 'secondaryName': 'Attended',
        }

    return {
        'campuses': comparison(campuses),
        'categories': comparison(categories),
        'monthly': trend(months),
        'weekly': trend(weeks),
        'sdgs': sorted(sdgs.items()),
        'activities': sorted(rows, key=lambda row: row['registrations'], reverse=True)[:10],
    }


def annual_plan_summary(year=None, campus_id=None):
    """Load annual goals with screen links in requests, plain summary otherwise.

    Convert invalid annual-year errors to HTTP 400; activity filters do not
    redefine the approved annual target scope.
    """
    from app.annual_goals import dashboard_context, summary
    from flask import has_request_context
    try:
        return dashboard_context(year, campus_id) if has_request_context() else summary(year, campus_id)
    except ValueError:
        from flask import abort
        abort(400, description='Choose a valid annual reporting year.')


def annual_plan_comparison(year=None):
    """Reuse annual-goal campus comparisons rather than recalculate achievement here."""
    from app.annual_goals import comparisons
    return comparisons(year)
