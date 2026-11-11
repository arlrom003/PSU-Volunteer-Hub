"""
Analytics Aggregator for PSU Volunteer Hub
===========================================
Read-only aggregates for director/coordinator views and historical exports.
Attendance totals count participation records, not distinct people, unless
explicitly stated. Each method documents its scope; not all share report filters.
"""
from datetime import datetime, timedelta
from app.models import db
from app.models.user import (User, Skill, Interest, user_skills,
                             user_interests)
from app.models.event import (Event, Registration, Attendance, Campus,
                               HistoricalActivity, ExternalParticipant)


class AnalyticsAggregator:
    """Group database records into display-ready counts without changing data."""

    @staticmethod
    def historical_summary(campus_id=None, start_year=None, end_year=None,
                           activity_type=None):
        """Summarize imported HistoricalActivity rows, separate from live events.

        Apply optional campus, inclusive year range, and exact activity-type
        filters to both row counts and reported volunteer totals. Sum reported
        participations, not unique volunteers; missing counts contribute no sum.
        Count distinct known years and flag each row missing a year or count once.
        Year filters exclude rows with unknown years; an empty sum becomes zero.
        """
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
        """Group filtered historical rows by source reporting-unit name.

        Use the same campus, inclusive year, and activity-type scope as the
        historical summary. SQL counts activities, sums reported participations,
        and counts rows missing a year or volunteer count. Convert empty sums
        to zero, then order units by participations descending. A person can
        contribute to several activity totals; these are not unique-person counts.
        """
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
        """Return two event-ID maps: registration counts and present attendance.

        Aggregate each table before joining so registrations and attendance do
        not multiply one another. Outer joins and COALESCE retain events with
        no records as zero. Registration totals include cancelled registrations;
        this helper serves the attendance snapshot, not filtered report KPIs.
        """
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
        """Build the coordinator snapshot from the latest event dates, limit 10.

        Scope by event campus when supplied; include future and past events,
        independently of report date/category filters. Use batched count maps
        and compute present attendance / all registrations * 100, rounded to
        one decimal place, or zero with no registrations. Counts are per event,
        not distinct people; cancelled registrations remain in the denominator.
        """
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
        """Count present account-linked attendance by non-null affiliation.

        Scope by the account's home campus and exact affiliation when supplied,
        not by the event's campus. Count all dates and account roles, with no
        report date/category filters. Repeated attendance by one person counts
        repeatedly; external participants have no User link and are excluded.
        Return affiliations ordered by attendance count descending.
        """
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
        """Rank profile skill selections by linked-account count, highest first.

        Count user_skills links per skill and return at most limit rows. No
        campus, role, active-account, or report-date filter applies. These are
        self-selected profile tags, not verified skills or attendance outcomes;
        this read-only summary does not change recommendation scoring.
        """
        rows = db.session.query(
            Skill.name, db.func.count(user_skills.c.user_id)
        ).join(user_skills, Skill.id == user_skills.c.skill_id
               ).group_by(Skill.name).order_by(
            db.func.count(user_skills.c.user_id).desc()).limit(limit).all()
        return [{'skill': name, 'volunteers': int(cnt)}
                for name, cnt in rows]

    @staticmethod
    def interest_distribution(limit=10):
        """Rank profile interest selections by linked-account count.

        Count user_interests links per interest, sort descending, and return
        at most limit rows. Include all linked accounts regardless of campus,
        role, active status, or report dates. Counts describe profile choices,
        not verified participation; one account can select several interests.
        """
        rows = db.session.query(
            Interest.name, db.func.count(user_interests.c.user_id)
        ).join(user_interests, Interest.id == user_interests.c.interest_id
               ).group_by(Interest.name).order_by(
            db.func.count(user_interests.c.user_id).desc()).limit(limit).all()
        return [{'interest': name, 'volunteers': int(cnt)}
                for name, cnt in rows]

    @staticmethod
    def role_demographics():
        """Return {role: account_count}, grouped across all stored User rows.

        Include inactive accounts and every campus, independently of report
        filters. These counts describe accounts, not attendance or registrations;
        external participants are separate records and do not appear here.
        """
        rows = db.session.query(User.role, db.func.count(
            User.id)).group_by(User.role).all()
        return {role: count for role, count in rows}

    @staticmethod
    def sex_participation(campus_id=None, start_date=None, end_date=None,
                          category=None, sex=None, activity_name=None, event_ids=None):
        """Combine present PSU and external attendance by recorded sex.

        Query PSU volunteer accounts directly through Attendance.user_id;
        query external participants through Registration, then merge counts.
        Both use event campus, category, literal title search, and event-ID scope.
        Dates refer to event dates: start inclusive, end inclusive via next-day
        exclusive bound; malformed dates are ignored. An empty event_ids list
        selects nothing, while None leaves event IDs unrestricted.

        Count attendance records, so repeat participants can count more than
        once. Keep 'Prefer Not to Say' separate from NULL ('Not recorded').
        Return fixed label order with zero-filled groups, or only the requested
        sex label when sex is supplied; unsupported labels yield no output rows.
        """
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
        """Build annual volunteer and campus Top 5 recognition lists.

        Use event dates from January 1 inclusive to next January 1 exclusive,
        independent of dashboard activity filters. Rank volunteer accounts by
        present attendance count, then completed-registration count, then name;
        user ID stabilizes selection when names also match. Show home campus.

        Rank official campuses by present account-linked attendance divided by
        non-cancelled account-linked registrations * 100 (one decimal place),
        then attendance count and name. Attribute these counts to event campus;
        omit campuses with no eligible registrations and exclude external rows.
        Rank equality uses numeric scores only, so names order tied rows without
        breaking shared ranks. Return at most five entries per list, even at ties.
        """
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
        """Assign competition ranks to already sorted rows, limited to five.

        Equal score-key tuples share rank; the next rank uses list position
        (1, 1, 3). Names are ordering tie-breakers, not ranking scores. Add rank
        to the supplied dictionaries in place; ties do not expand the cutoff.
        """
        previous, rank = None, 0
        for position, row in enumerate(rows[:5], start=1):
            score = tuple(row[key] for key in score_keys)
            if score != previous:
                rank = position
                previous = score
            row['rank'] = rank
        return rows[:5]

