import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    MILESTONE_MAX_BYTES = 10 * 1024 * 1024
    PRIVATE_UPLOAD_FOLDER = os.environ.get(
        'PRIVATE_UPLOAD_FOLDER', os.path.join(basedir, 'instance', 'uploads'))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60
    SESSION_IDLE_WARNING_SECONDS = 60
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx'}

    MAIL_PROVIDER = os.environ.get('MAIL_PROVIDER', 'smtp').lower()
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 25))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_TIMEOUT = 15
    MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get(
        'MAIL_DEFAULT_SENDER', 'noreply@psu.edu.ph')

    CAMPUSES = ['Lingayen', 'Urdaneta', 'Asingan', 'Bayambang',
                'Binmaley', 'Infanta', 'San Carlos', 'Santa Maria', 'Sta. Maria']

    EVENT_CATEGORIES = [
        'Environment',
        'Education & Literacy',
        'Health & Wellness',
        'Community Development',
        'Disaster Response',
        'Technology & Digital',
        'Arts & Culture',
        'Sports & Recreation'
    ]

    SKILL_CATEGORIES = [
        'Teaching/Tutoring',
        'Medical/First Aid',
        'Engineering/Construction',
        'IT/Computer Skills',
        'Organizational/Management',
        'Communication/Public Speaking',
        'Creative Arts/Design',
        'Agriculture/Farming',
        'Environmental Conservation',
        'Disaster Response',
        'Counseling/Psychology',
        'Languages/Translation'
    ]

    # Maps each volunteer interest (EVENT_CATEGORIES) to the skills that are
    # most relevant, so the onboarding wizard can reveal connected skills
    # directly when an interest is selected.
    INTEREST_SKILL_MAP = {
        'Environment': ['Environmental Conservation', 'Agriculture/Farming'],
        'Education & Literacy': [
            'Teaching/Tutoring', 'Communication/Public Speaking',
            'Languages/Translation'
        ],
        'Health & Wellness': ['Medical/First Aid', 'Counseling/Psychology'],
        'Community Development': [
            'Organizational/Management', 'Communication/Public Speaking',
            'Creative Arts/Design'
        ],
        'Disaster Response': [
            'Disaster Response', 'Medical/First Aid', 'Engineering/Construction'
        ],
        'Technology & Digital': [
            'IT/Computer Skills', 'Engineering/Construction', 'Creative Arts/Design'
        ],
        'Arts & Culture': [
            'Creative Arts/Design', 'Communication/Public Speaking'
        ],
        'Sports & Recreation': [
            'Organizational/Management', 'Communication/Public Speaking'
        ],
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL',
                                             'mysql+pymysql://root:@localhost/psu_volunteer_hub')
    MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'true').lower() == 'true'
    MAIL_DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # NOTE: Must never raise at import time — that would break test/CLI
    # collection whenever DATABASE_URL is unset. Enforcement happens in
    # create_app() when the production config is actually selected.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    TRUSTED_PROXY_COUNT = int(os.environ.get('TRUSTED_PROXY_COUNT', '1'))


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
