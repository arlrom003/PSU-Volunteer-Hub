"""The fixed PSU campus catalogue and its database reference records."""
from app.models import db
from app.models.event import Campus


PSU_CAMPUSES = (
    ('Lingayen', 'LINGAYEN'),
    ('Urdaneta', 'URDANETA'),
    ('Asingan', 'ASINGAN'),
    ('Bayambang', 'BAYAMBANG'),
    ('Binmaley', 'BINMALEY'),
    ('Infanta', 'INFANTA'),
    ('San Carlos', 'SANCARLOS'),
    ('Santa Maria', 'STAMARIA'),
    ('Alaminos', 'ALAMINOS'),
)

PSU_CAMPUS_AFFILIATIONS = {
    'LINGAYEN': (
        'College of Arts, Sciences and Letters (CASL)',
        'College of Business and Public Administration (CBPA)',
        'College of Computing Sciences (CCS)',
        'College of Hospitality and Tourism Management (CHTM)',
        'College of Teacher Education (CTE)',
        'College of Industrial Technology (CIT)',
    ),
    'URDANETA': (
        'College of Computing (CC)',
        'College of Engineering and Architecture (CEA)',
        'College of Arts and Education (CAE)',
    ),
    'ASINGAN': ('College of Technology and Business (CTB)', 'College of Education (COE)'),
    'BAYAMBANG': (
        'College of Teacher Education (CTE)',
        'College of Arts, Sciences and Technology (CAST)',
        'Institute of Nursing (ION)',
    ),
    'BINMALEY': (
        'College of Fisheries and Environmental Sciences',
        'College of Criminal Justice Education',
        'College of General and Teacher Education',
    ),
    'INFANTA': ('College of Business and Agriculture Management', 'College of Teacher Education'),
    'SANCARLOS': (
        'College of Hospitality Management, Business and Computing',
        'College of Teacher Education',
        'College of Agriculture',
    ),
    'STAMARIA': ('College of Agriculture', 'College of Teacher Education'),
    'ALAMINOS': ('College of Management and Technology (CMT)', 'College of Teacher Education (CTE)'),
}


def campus_affiliations(campus):
    """Return the fixed affiliation choices for an official campus."""
    code = getattr(campus, 'code', campus)
    return list(PSU_CAMPUS_AFFILIATIONS.get(code, ()))


def campus_query():
    return Campus.query.filter(db.or_(*[
        db.and_(Campus.name == name, Campus.code == code)
        for name, code in PSU_CAMPUSES]))


def campus_rows():
    from app.performance import request_value
    return request_value('official-campus-rows', lambda: campus_query().order_by(Campus.name, Campus.id).all())


def validate_catalogue():
    rows = Campus.query.all()
    unsupported = [row for row in rows if (row.name, row.code) not in PSU_CAMPUSES]
    if unsupported:
        labels = ', '.join(f'{row.name} ({row.code}, ID {row.id})' for row in unsupported)
        raise ValueError(f'Unsupported PSU campus records: {labels}. '
                         'Review and migrate these records and their references before starting the app. '
                         'No records have been deleted or reassigned.')
    return rows


def seed_catalogue(commit=True):
    rows = validate_catalogue()
    existing = {row.code for row in rows}
    for name, code in PSU_CAMPUSES:
        if code not in existing:
            db.session.add(Campus(name=name, code=code))
    if commit:
        db.session.commit()


def official_campus(campus_id):
    if not isinstance(campus_id, int) or not 1 <= campus_id <= 2147483647:
        return None
    row = db.session.get(Campus, campus_id)
    return row if row and (row.name, row.code) in PSU_CAMPUSES else None
