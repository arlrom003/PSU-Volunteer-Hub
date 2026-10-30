"""Presentation summaries derived from the same rows as PDF and CSV reports."""

from calendar import monthrange
from datetime import datetime, timedelta


ATTENTION_LABELS = {
    'pending_attendance': 'Attendance awaiting completion',
    'low_attendance': 'Attendance below the 75% review guide',
    'missed_targets': 'Participant targets not reached',
}


def resolve_period(args, now=None):
    """Resolve explicit dates before presets; never overwrite bookmarked ranges."""
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
        f'From {start}' if start else f'Until {end}' if end else 'All dates')
    return {'value': period, 'start': start, 'end': end, 'label': label,
            'comparison': comparison}


def performance_summary(rows, show_targets=True):
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
    """Reuse report rows for findings, metrics, comparisons and export links."""
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
    return dict(evidence_rows=rows, evidence_summary=summary, performance=performance,
                period=period, deltas=deltas, attention_labels=ATTENTION_LABELS,
                attention_items=consolidate_attention(performance))


def consolidate_attention(performance, pending=None):
    """Keep one actionable row per activity, retaining every reason for review."""
    items = {}
    groups = [('pending', performance['pending'] if pending is None else pending),
              ('missed', performance['missed']), ('low', performance['low'])]
    for kind, rows in groups:
        for row in rows:
            item = items.setdefault(row['event_id'], dict(row, reasons=[], is_pending=False))
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
    """Group existing report counts without querying or changing their meaning."""
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
    from app.annual_goals import dashboard_context, summary
    from flask import has_request_context
    try:
        return dashboard_context(year, campus_id) if has_request_context() else summary(year, campus_id)
    except ValueError:
        from flask import abort
        abort(400, description='Choose a valid annual reporting year.')


def annual_plan_comparison(year=None):
    from app.annual_goals import comparisons
    return comparisons(year)
