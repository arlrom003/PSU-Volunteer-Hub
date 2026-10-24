"""Dashboard comparisons must retain the report's scope and counting units."""
from datetime import datetime

from app.dashboard import summarize_report, summarize_leadership_attention


def test_comparisons_and_trends_use_the_same_report_counts():
    rows = [
        {'campus': 'Lingayen', 'category': 'Environment',
         'date': datetime(2026, 1, 3), 'registrations': 4, 'attended': 3,
         'sdgs': 'SDG 13, SDG 15'},
        {'campus': 'Urdaneta', 'category': 'Education',
         'date': datetime(2026, 1, 4), 'registrations': 2, 'attended': 1,
         'sdgs': 'SDG 4'},
    ]
    data = summarize_report(rows)
    assert sum(item['registrations'] for item in data['campuses']) == 6
    assert sum(item['attended'] for item in data['categories']) == 4
    assert data['monthly']['primary'] == [6]
    assert data['monthly']['secondary'] == [4]
    assert data['campuses'][0]['rate'] == 75.0
    assert data['sdgs'] == [('SDG 13', 1), ('SDG 15', 1), ('SDG 4', 1)]
    assert rows[0]['registrations'] == 4


def test_empty_dashboard_data_has_explicit_empty_series():
    data = summarize_report([])
    assert data['campuses'] == []
    assert data['categories'] == []
    assert data['monthly']['labels'] == []
    assert data['weekly']['secondary'] == []
    assert data['activities'] == []


def test_filtered_input_does_not_restore_other_campus_or_category_records():
    rows = [{'campus': 'Lingayen', 'category': 'Environment',
             'date': datetime(2026, 1, 1), 'registrations': 0, 'attended': 0,
             'sdgs': 'Not tagged'}]
    data = summarize_report(rows)
    assert [item['label'] for item in data['campuses']] == ['Lingayen']
    assert [item['label'] for item in data['categories']] == ['Environment']
    assert data['campuses'][0]['rate'] == 0
    assert data['weekly']['labels'] == ['2026-W01']


def test_leadership_attention_uses_live_decision_thresholds():
    class CampusStub:
        def __init__(self, campus_id):
            self.id = campus_id

    summary = summarize_leadership_attention(
        [{'registrations': 4, 'attendance_rate': 74.9},
         {'registrations': 0, 'attendance_rate': 0},
         {'registrations': 5, 'attendance_rate': 75}],
        [{'target': 10, 'actual': 9}, {'target': 10, 'actual': 10},
         {'target': None, 'actual': 0}],
        attendance_pending=2,
        all_campuses=[CampusStub(1), CampusStub(2), CampusStub(3)],
        active_campus_ids={1, 3})

    assert summary == {
        'low_attendance': 1,
        'below_target': 1,
        'attendance_pending': 2,
        'no_recent_activity': 1,
        'total': 5,
    }
