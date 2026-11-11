"""Verify profile account controls in an isolated local app and Chromium."""
import json
import logging
from pathlib import Path
import sys
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.models import db
from app.models.user import User
from app.campuses import campus_rows, campus_affiliations


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app('testing')
    with app.app_context():
        user = User.query.filter_by(email='student@psu.edu').one()
        user.sex = 'prefer_not_to_say'
        user.set_password('OriginalPassword1!')
        db.session.commit()
        identity = user.id
        target = next(c for c in campus_rows() if c.id != user.campus_id)
        campus_id, college = str(target.id), campus_affiliations(target)[0]
        cookie = app.session_interface.get_signing_serializer(app).dumps(dict(
            _user_id=str(user.id), _fresh=True, auth_version=user.auth_version))
    server = make_server('127.0.0.1', 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors, checks = [], []
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies([dict(name='session', value=cookie, url=base)])
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            for width in (1440, 900, 768, 390, 320):
                page.set_viewport_size(dict(width=width, height=1000))
                assert page.goto(base+'/profile').status == 200
                for section in ('name', 'campus', 'password'):
                    disclosure = page.locator('#change-'+section)
                    control = disclosure.locator('summary')
                    control.focus()
                    assert control.evaluate('(el) => el.matches(":focus-visible")')
                    control.press('Enter')
                    assert disclosure.get_attribute('open') is not None
                    assert control.bounding_box()['height'] >= 44
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'), width
                assert page.locator('.profile-account-section').evaluate_all('''sections =>
                    sections.every(section => [...section.querySelectorAll('input, select, button')]
                        .filter(control => !control.hidden && control.type !== 'hidden')
                        .every(control => control.getBoundingClientRect().height >= 44))''')
                assert page.locator('#account-current_password').get_attribute('autocomplete') == 'current-password'
                assert page.locator('#account-new_password').get_attribute('autocomplete') == 'new-password'
                page.get_by_role('button', name='Show new password', exact=True).click()
                assert page.locator('#account-new_password').get_attribute('type') == 'text'
                if width in (1440, 390):
                    page.evaluate('document.activeElement.blur(); window.scrollTo(0, 0)')
                    page.screenshot(path=f'.qa-profile-settings-{width}.png', full_page=True)
                    if width == 1440:
                        for section in ('name', 'campus', 'password'):
                            page.locator('#change-'+section+' summary').click()
                        page.evaluate('document.activeElement.blur(); window.scrollTo(0, 0)')
                        page.screenshot(path='.qa-profile-settings-preview.png')
                checks.append(dict(width=width, keyboard=True, overflow=False))
            page.locator('#account-campus_id').select_option(campus_id)
            assert page.locator('#account-college_affiliation').input_value() == ''
            page.locator('#account-college_affiliation').select_option(college)
            with page.expect_navigation():
                page.get_by_role('button', name='Save campus', exact=True).click()
            assert page.locator('#change-campus').get_attribute('open') is not None
            with app.app_context():
                assert db.session.get(User, identity).campus_id == int(campus_id)
            page.locator('#change-password summary').click()
            page.locator('#account-current_password').fill('WrongPassword1!')
            page.locator('#account-new_password').fill('UpdatedPassword2!')
            page.locator('#account-password_confirmation').fill('UpdatedPassword2!')
            with page.expect_navigation():
                page.get_by_role('button', name='Change password', exact=True).click()
            assert page.locator('[data-profile-errors]').evaluate('(el) => el===document.activeElement')
            assert page.locator('#change-password').get_attribute('open') is not None
            assert page.locator('#account-current_password').input_value() == ''
            page.locator('#change-name summary').click()
            page.locator('#account-name').fill('Unsaved name')
            page.locator('input[name="interests"]').first.click()
            dialogs = []
            def cancel(dialog):
                dialogs.append(dialog.type)
                dialog.dismiss()
            page.on('dialog', cancel)
            page.get_by_role('button', name='Save name', exact=True).click()
            page.wait_for_function('!document.querySelector("#change-name form").hasAttribute("aria-busy")')
            assert dialogs == ['beforeunload']
            with app.app_context():
                assert db.session.get(User, identity).name != 'Unsaved name'
            page.get_by_role('button', name='Save name', exact=True).click()
            assert len(dialogs) == 2
            page.remove_listener('dialog', cancel)
            page.once('dialog', lambda dialog: dialog.accept())
            native = browser.new_context(java_script_enabled=False)
            native.add_cookies([dict(name='session', value=cookie, url=base)])
            native_page = native.new_page()
            assert native_page.goto(base+'/profile').status == 200
            native_page.locator('#change-password summary').click()
            assert not native_page.locator('[data-profile-password]').first.is_visible()
            native.close()
            browser.close()
        assert not errors, errors
        print(json.dumps(dict(checks=checks, campus_save=True, inline_errors=True,
                             unsaved_guard=True, page_errors=errors), indent=2))
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
