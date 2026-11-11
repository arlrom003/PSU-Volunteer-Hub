"""
Analytics Aggregator for PSU Volunteer Hub
===========================================
Builds aggregate query results used by the director dashboard.
All methods are static — no state, pure aggregation queries.
"""
from datetime import datetime, timedelta
from app.models import db
from app.models.user import (User, Skill, Interest, user_skills,
                             user_interests)
from app.models.event import (Event, Registration, Attendance, Campus,
                               HistoricalActivity, ExternalParticipant)


class AnalyticsAggregator:
    """Produces pre-aggregated data for director analytics views."""

    @staticmethod
    def historical_summary(campus_id=None, start_year=None, end_year=None,
                           activity_type=None):
        """Return aggregate counts imported from audited legacy reports."""
        query = HistoricalActivity.query
        volunteer_query = db.session.query(
            db.func.sum(HistoricalActivity.volunteer_count))
        if campus_id:
            query = query.filter_by(campus_id=campus_id)
            volunteer_query = volunteer_query.filter(
                HistoricalActivity.campus_id == campus_id)
        if start_year:
            query = query.filter(HistoricalActivity.year_conducted >= start_year)
            volunteer_query = volunteer_query.filter(
                HistoricalActivity.year_conducted >= start_year)
        if end_year:
            query = query.filter(HistoricalActivity.year_conducted <= end_year)
            volunteer_query = volunteer_query.filter(
                HistoricalActivity.year_conducted <= end_year)
        if activity_type:
            query = query.filter(HistoricalActivity.activity_type == activity_type)
            volunteer_query = volunteer_query.filter(
                HistoricalActivity.activity_type == activity_type)
        return {
            'activities': query.count(),
            'volunteer_participations': int(volunteer_query.scalar() or 0),
            'years_covered': query.with_entities(
                HistoricalActivity.year_conducted)
                .filter(HistoricalActivity.year_conducted.isnot(None))
                .distinct().count(),
            'incomplete_records': query.filter(db.or_(
                HistoricalActivity.year_conducted.is_(None),
                HistoricalActivity.volunteer_count.is_(None))).count(),
        }

    @staticmethod
    def historical_campus_stats(campus_id=None, start_year=None, end_year=None,
                                activity_type=None):
        """Return aggregate activity and participation totals by reporting unit."""
        query = db.session.query(
            HistoricalActivity.unit_name,
            db.func.count(HistoricalActivity.id),
            db.func.sum(HistoricalActivity.volunteer_count),
            db.func.sum(db.case((db.or_(
                HistoricalActivity.year_conducted.is_(None),
                HistoricalActivity.volunteer_count.is_(None)), 1), else_=0)),
        )
        if campus_id:
            query = query.filter(HistoricalActivity.campus_id == campus_id)
        if start_year:
            query = query.filter(HistoricalActivity.year_conducted >= start_year)
        if end_year:
            query = query.filter(HistoricalActivity.year_conducted <= end_year)
        if activity_type:
            query = query.filter(HistoricalActivity.activity_type == activity_type)
        rows = query.group_by(HistoricalActivity.unit_name).all()
        results = [{
            'campus': unit,
            'activities': int(activities),
            'participations': int(participations or 0),
            'incomplete_records': int(incomplete or 0),
        } for unit, activities, participations, incomplete in rows]
        results.sort(key=lambda row: row['participations'], reverse=True)
        return results

    @staticmethod
    def _event_attendance_counts(events):
        event_ids = [event.id for event in events]
        registrations = db.session.query(Registration.event_id.label('event_id'),
            db.func.count(Registration.id).label('total')).filter(Registration.event_id.in_(event_ids)
        ).group_by(Registration.event_id).subquery()
        attendance = db.session.query(Attendance.event_id.label('event_id'),
            db.func.count(Attendance.id).label('total')).filter(
            Attendance.event_id.in_(event_ids), Attendance.status == 'present'
        ).group_by(Attendance.event_id).subquery()
        counts = db.session.query(Event.id, db.func.coalesce(registrations.c.total, 0),
            db.func.coalesce(attendance.c.total, 0)).outerjoin(
            registrations, registrations.c.event_id == Event.id).outerjoin(
            attendance, attendance.c.event_id == Event.id).filter(Event.id.in_(event_ids)).all()
        return {row[0]: row[1] for row in counts}, {row[0]: row[2] for row in counts}

    @staticmethod
    def attendance_summary(campus_id=None, limit=10):
        """Return [{event, registered, attended, rate}] for completed/upcoming events."""
        event_query = Event.query
        if campus_id:
            event_query = event_query.filter_by(campus_id=campus_id)
        events = event_query.order_by(Event.date.desc()).limit(limit).all()
        registrations, attendance = AnalyticsAggregator._event_attendance_counts(events)

        results = []
        for e in events:
            registered = registrations.get(e.id, 0)
            attended = attendance.get(e.id, 0)
            rate = round((attended / registered * 100),
                         1) if registered > 0 else 0
            results.append({'event': e, 'registered': registered,
                           'attended': attended, 'rate': rate})
        return results

    @staticmethod
    def department_participants(campus_id=None, department=None):
        """Participant affiliations available for the selected campus only."""
        query = db.session.query(
            User.college_affiliation, db.func.count(Attendance.id)
        ).join(Attendance, Attendance.user_id == User.id).filter(
            Attendance.status == 'present', User.college_affiliation.isnot(None))
        if campus_id:
            query = query.filter(User.campus_id == campus_id)
        if department:
            query = query.filter(User.college_affiliation == department)
        return [{'department': name, 'actual_participants': int(count)}
                for name, count in query.group_by(User.college_affiliation)
                .order_by(db.func.count(Attendance.id).desc()).all()]

    @staticmethod
    def skill_distribution(limit=10):
        """Most common volunteer skills (descriptive only; does not alter the
        recommendation engine)."""
        rows = db.session.query(
            Skill.name, db.func.count(user_skills.c.user_id)
        ).join(user_skills, Skill.id == user_skills.c.skill_id
               ).group_by(Skill.name).order_by(
            db.func.count(user_skills.c.user_id).desc()).limit(limit).all()
        return [{'skill': name, 'volunteers': int(cnt)}
                for name, cnt in rows]

    @staticmethod
    def interest_distribution(limit=10):
        """Most common volunteer interests (descriptive only)."""
        rows = db.session.query(
            Interest.name, db.func.count(user_interests.c.user_id)
        ).join(user_interests, Interest.id == user_interests.c.interest_id
               ).group_by(Interest.name).order_by(
            db.func.count(user_interests.c.user_id).desc()).limit(limit).all()
        return [{'interest': name, 'volunteers': int(cnt)}
                for name, cnt in rows]

    @staticmethod
    def role_demographics():
        """Return dict of {role: count} across all users."""
        rows = db.session.query(User.role, db.func.count(
            User.id)).group_by(User.role).all()
        return {role: count for role, count in rows}

    @staticmethod
    def sex_participation(campus_id=None, start_date=None, end_date=None,
                          category=None, sex=None, activity_name=None, event_ids=None):
        """Verified PSU and external attendance grouped by recorded sex."""
        query = db.session.query(User.sex, db.func.count(Attendance.id)).join(
            Attendance, Attendance.user_id == User.id).join(
            Event, Event.id == Attendance.event_id).filter(
                User.role == 'volunteer', Attendance.status == 'present')
        if event_ids is not None:
            query = query.filter(Event.id.in_(event_ids))
        if activity_name and activity_name.strip():
            query = query.filter(Event.title.icontains(activity_name.strip(), autoescape=True))
        if campus_id:
            query = query.filter(Event.campus_id == campus_id)
        if start_date:
            try:
                query = query.filter(Event.date >= datetime.fromisoformat(start_date))
            except ValueError:
                start_date = None
        if end_date:
            try:
                query = query.filter(Event.date < datetime.fromisoformat(end_date) + timedelta(days=1))
            except ValueError:
                end_date = None
        if category:
            query = query.filter(Event.category == category)
        if sex in ('male', 'female', 'prefer_not_to_say'):
            query = query.filter(User.sex == sex)
        rows = {value: int(count) for value, count in query.group_by(User.sex).all()}
        external_query = db.session.query(
            ExternalParticipant.sex, db.func.count(Attendance.id)
        ).join(Registration, Registration.external_participant_id == ExternalParticipant.id).join(
            Attendance, Attendance.registration_id == Registration.id
        ).join(Event, Event.id == Attendance.event_id).filter(
            Attendance.status == 'present')
        if event_ids is not None:
            external_query = external_query.filter(Event.id.in_(event_ids))
        if activity_name and activity_name.strip():
            external_query = external_query.filter(Event.title.icontains(activity_name.strip(), autoescape=True))
        if campus_id:
            external_query = external_query.filter(Event.campus_id == campus_id)
        if start_date:
            try:
                external_query = external_query.filter(Event.date >= datetime.fromisoformat(start_date))
            except ValueError:
                pass
        if end_date:
            try:
                external_query = external_query.filter(Event.date < datetime.fromisoformat(end_date) + timedelta(days=1))
            except ValueError:
                pass
        if category:
            external_query = external_query.filter(Event.category == category)
        if sex in ('male', 'female', 'prefer_not_to_say'):
            external_query = external_query.filter(ExternalParticipant.sex == sex)
        for value, count in external_query.group_by(ExternalParticipant.sex).all():
            rows[value] = rows.get(value, 0) + int(count)
        labels = (
            ('female', 'Female'),
            ('male', 'Male'),
            ('prefer_not_to_say', 'Prefer Not to Say'),
            (None, 'Not recorded'),
        )
        return [{'sex': label, 'actual_participants': rows.get(value, 0)}
                for value, label in labels if sex is None or value == sex]

    @staticmethod
    def award_leaderboards(year):
        """Return the annual, verified-participation Top 5 recognition lists."""
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        completed_counts = db.session.query(
            Registration.user_id.label('user_id'), db.func.count(Registration.id).label('completed')
        ).join(Event).filter(Registration.status == 'completed', Event.date >= start, Event.date < end
        ).group_by(Registration.user_id).subquery()
        attended = db.func.count(Attendance.id)
        completed = db.func.coalesce(completed_counts.c.completed, 0)
        name_order = User.name.collate('utf8mb4_bin' if db.engine.dialect.name in ('mysql', 'mariadb') else 'BINARY')
        volunteers = db.session.query(
            User.id, User.name, Campus.name,
            attended.label('attendance'), completed
        ).join(Attendance, Attendance.user_id == User.id).join(
            Event, Event.id == Attendance.event_id).outerjoin(
            Campus, Campus.id == User.campus_id).outerjoin(
            completed_counts, completed_counts.c.user_id == User.id).filter(
                User.role == 'volunteer', Attendance.status == 'present',
                Event.date >= start, Event.date < end).group_by(
                    User.id, User.name, Campus.name, completed_counts.c.completed).order_by(
                        attended.desc(), completed.desc(), name_order, User.id).limit(5).all()
        volunteer_rows = []
        for user_id, name, campus, attendance, completed in volunteers:
            volunteer_rows.append({'name': name, 'campus': campus or 'Unassigned',
                                   'attendance': int(attendance), 'completed': completed})
        volunteer_rows.sort(key=lambda row: (-row['attendance'], -row['completed'], row['name']))

        campus_registrations = dict(db.session.query(
            Event.campus_id, db.func.count(Registration.id)).join(
            Registration, Registration.event_id == Event.id).filter(
            Registration.user_id.isnot(None), Registration.status != 'cancelled',
            Event.date >= start, Event.date < end).group_by(Event.campus_id).all())
        campus_attendance = dict(db.session.query(
            Event.campus_id, db.func.count(Attendance.id)).join(
            Attendance, Attendance.event_id == Event.id).filter(
            Attendance.user_id.isnot(None), Attendance.status == 'present',
            Event.date >= start, Event.date < end).group_by(Event.campus_id).all())
        campus_rows = []
        from app.campuses import campus_rows as official_campuses
        for campus in official_campuses():
            registrations = campus_registrations.get(campus.id, 0)
            if not registrations:
                continue
            attended = campus_attendance.get(campus.id, 0)
            campus_rows.append({'name': campus.name, 'registrations': registrations,
                                'attendance': attended,
                                'rate': round(attended / registrations * 100, 1)})
        campus_rows.sort(key=lambda row: (-row['rate'], -row['attendance'], row['name']))
        return {
            'volunteers': AnalyticsAggregator._rank_top_five(volunteer_rows, ('attendance', 'completed')),
            'campuses': AnalyticsAggregator._rank_top_five(campus_rows, ('rate', 'attendance')),
        }

    @staticmethod
    def _rank_top_five(rows, score_keys):
        previous, rank = None, 0
        for position, row in enumerate(rows[:5], start=1):
            score = tuple(row[key] for key in score_keys)
            if score != previous:
                rank = position
                previous = score
            row['rank'] = rank
        return rows[:5]

