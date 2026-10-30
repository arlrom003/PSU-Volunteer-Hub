import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _template(path):
    return (ROOT / 'templates' / path).read_text(encoding='utf-8')


def test_operational_tables_keep_visible_mobile_labels():
    templates = {
        'coordinator/Coordinator_dash.html': ('data-label="Activity"', 'data-label="Actions"'),
        'coordinator/attendance_MnGmt.html': ('data-label="Volunteer"', 'data-label="Status"'),
        'admin/Admin_mngmt_dash.html': ('data-label="User"', 'data-label="Actions"'),
        'volunteer/Volunteer_Profile.html': ('data-label="Activity"', 'data-label="Certificate"'),
    }

    for path, labels in templates.items():
        content = _template(path)
        assert 'table-scroll--record' in content
        assert 'data-table--record' in content
        assert all(label in content for label in labels)
        assert '<th scope="col">' in content


def test_report_tables_keep_scroll_guidance_and_semantics():
    templates = (
        'coordinator/coordinator_analytics.html',
        'director/Director_impact_anlaytics_dash.html',
        'admin/Admin_mngmt_dash.html',
        'admin/policy_management.html',
        'admin/terms_management.html',
    )

    for path in templates:
        content = _template(path)
        assert 'table-scroll--report' in content
        assert 'data-table--report' in content
        assert 'aria-describedby=' in content
        assert 'Swipe horizontally to view remaining columns.' in content
        for hint in re.finditer(r'<p class="table-scroll__hint" id="([^"]+)">', content):
            assert content.find(f'aria-describedby="{hint.group(1)}"', hint.end()) > hint.end()


def test_shared_styles_reflow_records_and_contain_reports():
    css = (ROOT / 'static' / 'styles' / 'role-shell.css').read_text(encoding='utf-8')
    for selector in (
        '.table-scroll--record',
        '.data-table--record td::before',
        '.data-table--report',
        '.table-scroll__hint',
        '.table-scroll--report',
    ):
        assert selector in css


def test_activity_workspace_groups_secondary_and_destructive_actions():
    content = _template('coordinator/Coordinator_dash.html')

    assert 'More actions<span class="sr-only"> for {{ event.title }}</span>' in content
    assert 'Edit activity' in content
    assert 'Upload milestone' in content
    assert 'Publish announcement' in content
    assert 'Remove activity' in content
    assert content.index('Publish announcement') < content.index('Remove activity')


def test_director_campus_coverage_reflows_without_extra_tables():
    content = _template('director/Director_Dash.html')
    styles = (ROOT / 'static' / 'styles' / 'role-shell.css').read_text(encoding='utf-8')

    assert 'findings(attention_items' not in content
    assert 'campus_coverage' in content
    assert '.campus-coverage__campuses' in styles
    assert '@media (max-width: 640px)' in styles
