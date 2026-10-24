"""Presentation summaries derived from the same rows as PDF and CSV reports."""


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
            counts = groups.setdefault(key, {'registrations': 0, 'attended': 0})
            counts['registrations'] += row['registrations']
            counts['attended'] += row['attended']
        for goal in row['sdgs'].split(', '):
            sdgs[goal] = sdgs.get(goal, 0) + 1

    def comparison(groups):
        return [
            {'label': label, **counts,
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


def summarize_leadership_attention(campus_rows, accomplishment_rows,
                                   attendance_pending, all_campuses,
                                   active_campus_ids):
    """Build the small live-data decision summary for the Director dashboard."""
    low_attendance = sum(
        1 for row in campus_rows
        if row['registrations'] and row['attendance_rate'] < 75
    )
    below_target = sum(
        1 for row in accomplishment_rows
        if row['target'] is not None and row['actual'] < row['target']
    )
    no_recent_activity = sum(
        1 for campus in all_campuses if campus.id not in active_campus_ids
    )
    return {
        'low_attendance': low_attendance,
        'below_target': below_target,
        'attendance_pending': attendance_pending,
        'no_recent_activity': no_recent_activity,
        'total': low_attendance + below_target + attendance_pending + no_recent_activity,
    }
