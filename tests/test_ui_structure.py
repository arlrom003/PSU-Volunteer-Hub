"""Structural regression checks for the shared Bare CSS interface."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def _templates():
    return list(TEMPLATES.rglob("*.html"))


def test_tailwind_is_not_loaded():
    markup = "\n".join(path.read_text(encoding="utf-8") for path in _templates())
    assert "cdn.tailwindcss.com" not in markup
    assert "tailwind.config" not in markup


def test_templates_inherit_a_shared_layout():
    pages = [path for path in _templates()
             if "layouts" not in path.parts and "partials" not in path.parts]
    for page in pages:
        assert "{% extends" in page.read_text(encoding="utf-8"), page


def test_role_styles_and_local_assets_exist():
    styles = ROOT / "static" / "styles"
    for name in ("base", "volunteer", "coordinator", "director", "admin",
                 "public", "auth"):
        assert (styles / f"{name}.css").is_file()
    assets = ROOT / "static" / "assets"
    assert (assets / "PSU-logo.png").is_file()
    assert (assets / "temp_profile.jpg").is_file()


def test_director_menu_has_no_admin_only_items():
    sidebar = (TEMPLATES / "partials" / "sidebar.html").read_text(encoding="utf-8")
    director = sidebar.split("current_user.role == 'director'", 1)[1].split(
        "current_user.role == 'admin'", 1)[0]
    assert "User Management" not in director
    assert "Settings" not in director


def test_admin_menu_hides_analytics_but_preserves_director_access():
    sidebar = (TEMPLATES / "partials" / "sidebar.html").read_text(encoding="utf-8")
    navigation = sidebar.split('<nav', 1)[1]
    director = navigation.split("current_user.role == 'director'", 1)[1].split(
        "{% else %}", 1)[0]
    admin = navigation.split("{% else %}", 1)[1].split("{% endif %}", 1)[0]
    assert "Analytics" in director
    assert "Analytics" not in admin


def test_mobile_sidebar_has_a_labeled_logout_action():
    sidebar = (TEMPLATES / "partials" / "sidebar.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles" / "role-shell.css").read_text(encoding="utf-8")

    assert 'class="role-user__logout"' in sidebar
    assert "Log out</span>" in sidebar
    assert ".role-user__logout" in styles
    assert "@media (max-width: 767px)" in styles


def test_public_navigation_stays_visible_during_scroll():
    styles = (ROOT / "static" / "styles" / "public.css").read_text(encoding="utf-8")
    nav = styles.split(".public-nav {", 1)[1].split("}", 1)[0]

    assert "position: sticky" in nav
    assert "top: 0" in nav
    assert "z-index:" in nav


def test_auth_navigation_stays_visible_during_scroll():
    styles = (ROOT / "static" / "styles" / "auth.css").read_text(encoding="utf-8")
    nav = styles.split(".auth-nav {", 1)[1].split("}", 1)[0]

    assert "position: sticky" in nav
    assert "top: 0" in nav
    assert "z-index:" in nav


def test_auth_navigation_has_brand_and_link_group():
    layout = (TEMPLATES / "layouts" / "auth_base.html").read_text(encoding="utf-8")

    assert 'class="auth-nav__brand"' in layout
    assert 'class="auth-nav__links"' in layout
    assert "url_for('home')" in layout
    assert "url_for('help_page')" in layout
    assert 'button button--secondary auth-nav__link' in layout


def test_auth_panel_uses_centered_logo_without_repeated_brand_name():
    partial = (TEMPLATES / "partials" / "auth_forms.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles" / "auth.css").read_text(encoding="utf-8")

    assert 'class="auth-brand__name"' not in partial
    identity = styles.split(".auth-identity {", 1)[1].split("}", 1)[0]
    assert "justify-content: center" in identity


def test_root_horizontal_containment_does_not_break_sticky_navigation():
    styles = (ROOT / "static" / "styles" / "base.css").read_text(encoding="utf-8")
    root = styles.split("html,\nbody {", 1)[1].split("}", 1)[0]

    assert "overflow-x: clip" in root


def test_flash_notifications_are_prominent_dismissible_and_in_flow():
    partial = (TEMPLATES / "partials" / "flash_messages.html").read_text(encoding="utf-8")
    base = (ROOT / "static" / "styles" / "base.css").read_text(encoding="utf-8")
    script = ROOT / "static" / "scripts" / "flash-messages.js"

    assert 'aria-label="Notifications"' in partial
    assert 'data-flash-dismiss' in partial
    assert 'category == \'session-expired\'' in partial
    assert "'alert' if urgent else 'status'" in partial
    assert ".flash-stack" in base and "margin: 1rem auto 0" in base
    assert "min-height: 44px" in base
    assert script.is_file()


def test_coordinator_sdg_choices_are_compact_and_mobile_safe():
    styles = (ROOT / "static" / "styles" / "coordinator.css").read_text(encoding="utf-8")
    assert ".choice-fieldset { display: block" in styles
    assert "display: flex; flex-wrap: wrap" in styles
    assert ".choice-fieldset .check-grid { width: 100%" in styles
    assert ".choice-fieldset .check-row" in styles
    assert "min-height: 44px" in styles
    assert "grid-template-columns: 1fr" in styles
