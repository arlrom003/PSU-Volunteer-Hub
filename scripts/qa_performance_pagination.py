"""Exercise paginated PSU workflows in an isolated browser and database."""
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.models import db
from app.models.user import User
from app.models.event import Event, Registration
from app.models.annual_plan import AnnualTarget
from tests.performance_fixture import build_performance_fixture


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app('testing')
    with app.app_context():
        build_performance_fixture(app)
        User.query.update({'first_use_guide_dismissed_at': datetime.now()})
        coordinator = User.query.filter_by(role='coordinator').first()
        activity = Event.query.filter(Event.campus_id == coordinator.campus_id,
                                     Event.end_date < datetime.now()).first()
        existing = db.session.query(Registration.user_id).filter_by(event_id=activity.id)
        for person in User.query.filter(User.role == 'volunteer', User.id.notin_(existing)).limit(15):
            db.session.add(Registration(user_id=person.id, event_id=activity.id, status='confirmed'))
        db.session.commit()
        activity_id = activity.id
        target_id = AnnualTarget.query.filter_by(campus_id=None).first().id
        people = dict(coordinator=coordinator, director=User.query.filter_by(role='director').first(),
                      admin=User.query.filter_by(role='admin').first(),
                      volunteer=User.query.filter_by(email='benchmark-0@example.test').one())
        serializer = app.session_interface.get_signing_serializer(app)
        cookies = {role: serializer.dumps(dict(_user_id=str(person.id), _fresh=True,
                   auth_version=person.auth_version)) for role, person in people.items()}
    server = make_server('127.0.0.1', 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    checks, errors = [], []
    routes = [('volunteer', '/notifications', 'Notification pages'),
              ('admin', '/admin_dash?tab=users', 'User pages'),
              ('volunteer', '/volunteer_dash', 'Registration history pages'),
              ('coordinator', '/coordinator_dash?period=all&status=all', 'Campus activity pages'),
              ('coordinator', f'/attendance?event_id={activity_id}', 'Attendance participant pages'),
              ('coordinator', '/coordinator_analytics?period=all', 'Campus report pages'),
              ('director', f'/annual-goals/targets/{target_id}/activities', 'Linked goal activity pages'),
              ('director', '/analytics?period=all', 'Live Activity Report Pages')]
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            for width in (1440, 900, 768, 390, 320):
                page.set_viewport_size(dict(width=width, height=1000))
                for role, path, label in routes:
                    context.clear_cookies()
                    context.add_cookies([dict(name=app.config['SESSION_COOKIE_NAME'], value=cookies[role], url=base)])
                    assert page.goto(base+path).status == 200, path
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'), (width, path)
                    disclosure = page.locator('details#detailed-report')
                    if disclosure.count() and disclosure.get_attribute('open') is None:
                        disclosure.locator(':scope > summary').click()
                    navigation = page.get_by_role('navigation', name=label, exact=True)
                    navigation.scroll_into_view_if_needed()
                    next_link = navigation.locator('a').last
                    box = next_link.bounding_box()
                    assert box['height'] >= 44 and box['width'] >= 44, (path, box)
                    page.keyboard.press('Tab')
                    next_link.focus()
                    assert next_link.evaluate('(element) => element.matches(":focus-visible")'), path
                    with page.expect_navigation():
                        next_link.press('Enter')
                    assert 'page=' in page.url
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'), (width, page.url)
                    checks.append(dict(width=width, path=path, keyboard_pagination=True, overflow=False))
                if width in (1440, 390):
                    page.screenshot(path=str(Path(__file__).resolve().parents[1]/f'.qa-performance-pagination-{width}.png'), full_page=True)
            context.clear_cookies()
            context.add_cookies([dict(name=app.config['SESSION_COOKIE_NAME'], value=cookies['coordinator'], url=base)])
            page.goto(base+f'/attendance?event_id={activity_id}')
            first = page.locator('[data-attendance-status]').first
            first.click()
            first.select_option('absent' if first.input_value() == 'present' else 'present')
            dialogs = []
            def retain_changes(dialog):
                dialogs.append(dialog.type)
                dialog.dismiss()
            page.on('dialog', retain_changes)
            page.get_by_role('navigation', name='Attendance participant pages').get_by_role('link', name='Next Page').click()
            assert dialogs == ['beforeunload']
            page.remove_listener('dialog', retain_changes)
            page.once('dialog', lambda dialog: dialog.accept())
            browser.close()
        assert not errors, errors
        print(json.dumps(dict(checks=checks, unsaved_attendance_guard=True, page_errors=errors), indent=2))
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
