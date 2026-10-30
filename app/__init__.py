"""
Flask Application Factory for PSU Volunteer Hub
=================================================
Creates and configures the Flask application instance.
"""
import os
from flask import Flask, request, redirect, url_for, session
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.orm import joinedload, selectinload
from app.models import db
from app.models.user import User, SystemSetting
from app.models.event import (Event, Registration, Attendance, Milestone,
                              Campus, ExternalParticipant, ActivityCategory, SdgGoal)
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.models.policy import (TermsRevision, TermsAcceptance, PrivacyRevision,
                               PrivacyAcknowledgement, ParticipationAgreementRevision)
from app.models.annual_plan import (AnnualPlan, AnnualIndicator, AnnualTarget, AnnualResult,
                                  AnnualActivityMapping, AnnualGoalProposal)
from config import config
from app.services.session_idle import check_inactivity, end_session, session_status


def create_app(config_name=None):
    """Create and return a configured Flask application instance."""
    config_name = config_name or os.environ.get('APP_ENV', 'development')
    if config_name not in config:
        raise ValueError('APP_ENV must be development, production, or testing')
    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static',
        static_url_path='/static'
    )

    # App configuration
    app.config.from_object(config[config_name])
    app.config['APP_ENV'] = config_name
    if config_name in ('development', 'default'):
        app.config['DEV_ERROR_DEBUGGER'] = os.environ.get('DEV_ERROR_DEBUGGER', 'false').lower() == 'true'
        app.config['PROPAGATE_EXCEPTIONS'] = app.config['DEV_ERROR_DEBUGGER']
    elif config_name == 'production':
        app.config.update(DEV_ERROR_DEBUGGER=False, PROPAGATE_EXCEPTIONS=False)
    timeout = app.config['SESSION_IDLE_TIMEOUT_SECONDS']
    warning = app.config['SESSION_IDLE_WARNING_SECONDS']
    if not (isinstance(timeout, int) and isinstance(warning, int)
            and 0 < warning < timeout):
        raise ValueError('Session warning must be positive and shorter than the idle timeout')

    if config_name == 'production':
        if not app.config.get('SQLALCHEMY_DATABASE_URI'):
            raise ValueError('DATABASE_URL must be set in production')
        if not app.config.get('SECRET_KEY'):
            raise ValueError('SECRET_KEY must be set in production')
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=app.config['TRUSTED_PROXY_COUNT'],
            x_proto=app.config['TRUSTED_PROXY_COUNT'])

    # app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///psu_volunteer_hub.db'
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # app.config['UPLOAD_FOLDER'] = 'static/uploads'
    # app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # Initialize extensions
    db.init_app(app)
    CSRFProtect(app)
    from app.errors import register_error_handlers
    register_error_handlers(app)

    @app.after_request
    def set_security_headers(response):
        public_asset = request.endpoint == 'favicon' or (
            request.endpoint == 'static' and
            (request.view_args or {}).get('filename', '').startswith(('styles/', 'scripts/', 'assets/')))
        if response.status_code >= 400 or (not public_asset and session.get('_user_id')) or request.endpoint in (
                'auth.session_activity', 'auth.login', 'auth.forgot_password', 'auth.reset_password'):
            response.headers['Cache-Control'] = 'no-store'
        if config_name == 'production':
            response.headers.setdefault('Content-Security-Policy',
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            response.headers.setdefault('Strict-Transport-Security',
                                        'max-age=31536000; includeSubDomains')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        return response

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def require_current_terms():
        """Keep authenticated users on the active Terms revision."""
        if request.endpoint in ('static', 'favicon') or getattr(request.routing_exception, 'code', None) == 404:
            return None
        if current_user.is_authenticated and session.get('auth_version') != current_user.auth_version:
            return end_session('Your session expired because your password was changed. Sign in again.')
        if current_user.is_authenticated:
            expired = check_inactivity()
            if expired is not None:
                return expired
        if (not current_user.is_authenticated
                or request.endpoint in ('static', 'auth.accept_terms',
                                        'auth.accept_privacy', 'auth.complete_sex',
                                        'auth.logout', 'auth.session_activity')):
            return None
        from app.models.policy import (TermsRevision, TermsAcceptance, PrivacyRevision,
                                       PrivacyAcknowledgement)
        revision = TermsRevision.query.filter_by(is_active=True).order_by(
            TermsRevision.published_at.desc()).first()
        if revision and not TermsAcceptance.query.filter_by(
                user_id=current_user.id, revision_id=revision.id).first():
            return redirect(url_for('auth.accept_terms'))
        privacy = PrivacyRevision.query.filter_by(is_active=True).order_by(
            PrivacyRevision.published_at.desc()).first()
        if privacy and not PrivacyAcknowledgement.query.filter_by(
                user_id=current_user.id, revision_id=privacy.id).first():
            session['privacy_next'] = request.full_path if request.query_string else request.path
            return redirect(url_for('auth.accept_privacy'))
        if current_user.role == 'volunteer' and not current_user.sex:
            return redirect(url_for('auth.complete_sex'))

    # Register blueprints
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    from app.routes.volunteer import volunteer_bp
    app.register_blueprint(volunteer_bp)
    from app.routes.coordinator import coordinator_bp
    app.register_blueprint(coordinator_bp)
    from app.routes.director import director_bp
    app.register_blueprint(director_bp)
    from app.routes.goals import goals_bp
    app.register_blueprint(goals_bp)
    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)
    from app.routes.events import events_bp
    app.register_blueprint(events_bp)
    from app.routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    @app.context_processor
    def inject_session_idle():
        if current_user.is_authenticated and 'last_activity_at' in session:
            return {'idle_session': session_status()}
        return {'idle_session': None}

    @app.context_processor
    def inject_notifications():
        from flask_login import current_user
        if current_user.is_authenticated:
            try:
                unread = Notification.query.filter_by(
                    user_id=current_user.id, is_read=False).count()
            except Exception:
                unread = 0
            return {'unread_notifications': unread}
        return {'unread_notifications': 0}

    from app.commands import register_commands
    register_commands(app)

    # Production schema and account provisioning are explicit deployment steps.
    if config_name != 'production':
        with app.app_context():
            db.create_all()
            _seed_campuses(app)
            _seed_interests_skills(app)
            _seed_sdgs(app)
            _seed_events(app)
            _seed_users(app)

    # Register root routes
    @app.route('/')
    def home():
        from flask import render_template
        from datetime import datetime
        from app.models.event import Event, HistoricalActivity

        now = datetime.now()
        featured_events = Event.query.filter(
            Event.date > now,
            Event.slots > 0,
        ).options(joinedload(Event.campus), selectinload(Event.registrations)
        ).order_by(Event.date.asc()).limit(6).all()
        completed_at = db.func.coalesce(Event.end_date, Event.date)
        completed_events = Event.query.filter(
            completed_at <= now,
        ).options(joinedload(Event.campus)).order_by(completed_at.desc(), Event.id.desc()).limit(3).all()
        historical_summary = {
            'activities': HistoricalActivity.query.count(),
            'participants': int(db.session.query(db.func.sum(
                HistoricalActivity.volunteer_count)).scalar() or 0),
        }
        return render_template(
            'Homepage.html',
            featured_events=featured_events,
            completed_events=completed_events,
            historical_summary=historical_summary,
        )

    @app.route('/historical-activities')
    def historical_activities():
        from flask import render_template, request
        from app.models.event import HistoricalActivity

        page = request.args.get('page', 1, type=int)
        pagination = HistoricalActivity.query.order_by(
            HistoricalActivity.year_conducted.desc(),
            HistoricalActivity.unit_name.asc(),
            HistoricalActivity.title.asc(),
        ).paginate(page=page, per_page=20, error_out=False)
        return render_template(
            'historical_activities.html',
            activities=pagination.items,
            current_page=pagination.page,
            total_pages=pagination.pages,
            total_count=pagination.total,
        )

    @app.route('/help')
    def help_page():
        from flask import render_template
        dashboard_url = None
        if current_user.is_authenticated:
            dashboard_routes = {
                'volunteer': 'events.volunteer_dash',
                'coordinator': 'coordinator.coordinator_dash',
                'director': 'director.director_dash',
                'admin': 'admin.admin_dash',
            }
            endpoint = dashboard_routes.get(current_user.role)
            if endpoint:
                dashboard_url = url_for(endpoint, tour=1)
        return render_template('help.html', dashboard_url=dashboard_url)

    @app.route('/favicon.ico')
    def favicon():
        """Use the bundled PSU mark for the browser tab icon."""
        from flask import send_from_directory
        return send_from_directory(
            app.static_folder,
            'assets/PSU-logo.png',
            mimetype='image/png',
        )

    @app.route('/dashboard')
    def dashboard():
        """Central dashboard router based on user role."""
        from flask import render_template, redirect, url_for
        from flask_login import current_user

        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        role_routes = {
            'volunteer': 'events.volunteer_dash',
            'coordinator': 'coordinator.coordinator_dash',
            'director': 'director.director_dash',
            'admin': 'admin.admin_dash',
        }
        route = role_routes.get(current_user.role, 'volunteer_dash')
        return redirect(url_for(route))

    return app


def _seed_interests_skills(app, commit=True):
    """Seed interest and skill lookup tables from config category lists."""
    from app.models.user import Interest, Skill
    from app.models.event import ActivityCategory
    from config import Config
    for name in getattr(Config, 'EVENT_CATEGORIES', []):
        if name and not Interest.query.filter_by(name=name).first():
            db.session.add(Interest(name=name))
        if name and not ActivityCategory.query.filter_by(name=name).first():
            db.session.add(ActivityCategory(name=name))
    if not ActivityCategory.query.filter_by(name='General').first():
        db.session.add(ActivityCategory(name='General'))
    for name in getattr(Config, 'SKILL_CATEGORIES', []):
        if name and not Skill.query.filter_by(name=name).first():
            db.session.add(Skill(name=name))
    if commit:
        db.session.commit()


def _seed_sdgs(app, commit=True):
    """Seed the fixed UN SDG catalogue used by activity forms and reports."""
    goals = (
        'No Poverty', 'Zero Hunger', 'Good Health and Well-Being',
        'Quality Education', 'Gender Equality', 'Clean Water and Sanitation',
        'Affordable and Clean Energy', 'Decent Work and Economic Growth',
        'Industry, Innovation and Infrastructure', 'Reduced Inequalities',
        'Sustainable Cities and Communities',
        'Responsible Consumption and Production', 'Climate Action',
        'Life Below Water', 'Life on Land',
        'Peace, Justice and Strong Institutions', 'Partnerships for the Goals',
    )
    for number, name in enumerate(goals, start=1):
        goal = SdgGoal.query.filter_by(number=number).first()
        if goal is None:
            db.session.add(SdgGoal(number=number, name=name))
        elif goal.name != name:
            goal.name = name
    if commit:
        db.session.commit()


def _seed_campuses(app, commit=True):
    """Seed campus data on first run."""
    from app.models.event import Campus
    if Campus.query.count() == 0:
        campuses = [
            Campus(name='Lingayen', code='LINGAYEN'),
            Campus(name='Urdaneta', code='URDANETA'),
            Campus(name='Asingan', code='ASINGAN'),
            Campus(name='Bayambang', code='BAYAMBANG'),
            Campus(name='Binmaley', code='BINMALEY'),
            Campus(name='Infanta', code='INFANTA'),
            Campus(name='San Carlos', code='SANCARLOS'),
            Campus(name='Santa Maria', code='STAMARIA'),
            Campus(name='Alaminos', code='ALAMINOS'),
        ]
        for campus in campuses:
            db.session.add(campus)
        if commit:
            db.session.commit()


def _seed_events(app):
    """Seed sample events for testing recommendations."""
    from app.models.event import Event
    if Event.query.count() == 0:
        from datetime import datetime, timedelta
        from app.models import db

        events = [
            Event(title='Youth Coding Mentor',
                  description='Help Grade 6 students at San Carlos Central School learn basic Python and logic.',
                  date=datetime.now() + timedelta(days=7),
                  category='Technology',
                  required_skills='Teaching, Python, Communication, Public Speaking',
                  slots=20, campus_id=1),
            Event(title='Green Campus Initiative',
                  description='Participate in our monthly tree planting and sustainable landscaping project.',
                  date=datetime.now() + timedelta(days=14),
                  category='Environment',
                  required_skills='Environmental Conservation, Agriculture, Leadership',
                  slots=50, campus_id=1),
            Event(title='Community Food Drive',
                  description='Help organize and distribute relief packages to affected local barangays.',
                  date=datetime.now() + timedelta(days=10),
                  category='Community',
                  required_skills='Organizational, Communication, Physical Fitness',
                  slots=30, campus_id=2),
            Event(title='Rural Literacy Program',
                  description='Teach foundational reading and mathematics to children in remote communities.',
                  date=datetime.now() + timedelta(days=21),
                  category='Education',
                  required_skills='Teaching, Tutoring, Communication, Patience',
                  slots=15, campus_id=1),
            Event(title='Disaster Response Training',
                  description='Participate in basic first aid and disaster preparedness workshop.',
                  date=datetime.now() + timedelta(days=5),
                  category='Health',
                  required_skills='Medical, First Aid, Disaster Response, Teamwork',
                  slots=40, campus_id=3),
            Event(title='Community IT Support Workshop',
                  description='Help bridge the digital divide by teaching elderly residents how to use modern tools.',
                  date=datetime.now() + timedelta(days=30),
                  category='Technology',
                  required_skills='IT, Computer Skills, Teaching, Patience, Communication',
                  slots=25, campus_id=4),
            Event(title='Coastal Cleanup Drive',
                  description='Monthly environmental drive to preserve the Lingayen coastline.',
                  date=datetime.now() + timedelta(days=3),
                  category='Environment',
                  required_skills='Environmental Conservation, Teamwork, Physical Fitness',
                  slots=100, campus_id=1),
            Event(title='Community Wellness Fair',
                  description='Assist medical personnel in organizing a free health mission.',
                  date=datetime.now() + timedelta(days=45),
                  category='Health',
                  required_skills='Medical, First Aid, Organizational, Communication',
                  slots=60, campus_id=7),
            Event(title='Sustainable Farming Demo',
                  description='Learn about organic cultivation and irrigation management.',
                  date=datetime.now() + timedelta(days=60),
                  category='Environment',
                  required_skills='Agriculture, Environmental Conservation, Teaching',
                  slots=30, campus_id=8),
        ]
        for event in events:
            db.session.add(event)
        db.session.commit()


def _seed_users(app):
    """Seed example users for all roles."""
    from app.models.user import User, VolunteerProfile, Skill, Interest
    from app.models import db

    if User.query.count() == 0:
        seed_users_data = [
            dict(name='Student Volunteer', email='student@psu.edu',
                 role='volunteer', campus_id=1),
            dict(name='Faculty Volunteer', email='faculty@psu.edu',
                 role='volunteer', campus_id=2),
            dict(name='Staff Volunteer', email='staff@psu.edu',
                 role='volunteer', campus_id=3),
            dict(name='Coordinator User', email='coordinator@psu.edu',
                 role='coordinator', campus_id=1),
            dict(name='Director User', email='director@psu.edu',
                 role='director', campus_id=1),
            dict(name='Admin User', email='admin@psu.edu',
                 role='admin', campus_id=1),
        ]
        for data in seed_users_data:
            u = User(name=data['name'], email=data['email'],
                     role=data['role'], campus_id=data['campus_id'])
            u.set_password('password')
            db.session.add(u)
            db.session.flush()

            if u.role == 'volunteer':
                # Instantiate VolunteerProfile without skills/interests kwargs
                profile = VolunteerProfile(user_id=u.id)
                db.session.add(profile)

                # Attach skills/interests directly to the user
                default_skills = [
                    'Teaching/Tutoring', 'Communication/Public Speaking',
                    'IT/Computer Skills']
                default_interests = [
                    'Education & Literacy', 'Technology & Digital',
                    'Environment']

                for sk_name in default_skills:
                    sk = Skill.query.filter_by(name=sk_name).first()
                    if not sk:
                        sk = Skill(name=sk_name)
                        db.session.add(sk)
                    u.skills.append(sk)

                for int_name in default_interests:
                    it = Interest.query.filter_by(name=int_name).first()
                    if not it:
                        it = Interest(name=int_name)
                        db.session.add(it)
                    u.interests.append(it)

        db.session.commit()
