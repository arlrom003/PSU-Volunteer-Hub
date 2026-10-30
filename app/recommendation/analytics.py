"""
Analytics Aggregator for PSU Volunteer Hub
===========================================
Builds aggregate query results used by the director dashboard.
All methods are static — no state, pure aggregation queries.
"""
from datetime import datetime, timedelta
import numpy as np
from sklearn.linear_model import LinearRegression
from app.models import db
from app.models.user import (User, Skill, Interest, user_skills,
                             user_interests)
from app.models.event import (Event, Registration, Attendance, Campus,
                               HistoricalActivity, ExternalParticipant)
from app.reports import build_events_report


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
    def historical_activity_type_stats(campus_id=None, start_year=None,
                                       end_year=None, activity_type=None):
        """Return historical participation totals grouped by activity type."""
        query = db.session.query(
            HistoricalActivity.activity_type,
            db.func.sum(HistoricalActivity.volunteer_count),
        )
        if campus_id:
            query = query.filter(HistoricalActivity.campus_id == campus_id)
        if start_year:
            query = query.filter(HistoricalActivity.year_conducted >= start_year)
        if end_year:
            query = query.filter(HistoricalActivity.year_conducted <= end_year)
        if activity_type:
            query = query.filter(HistoricalActivity.activity_type == activity_type)
        rows = query.group_by(HistoricalActivity.activity_type).all()
        results = [{
            'category': kind or 'Unspecified',
            'participations': int(participations or 0),
        } for kind, participations in rows]
        results.sort(key=lambda row: row['participations'], reverse=True)
        return results

    @staticmethod
    def campus_stats():
        """Return campus volunteer participation counts."""
        campuses = Campus.query.all()
        results = []
        for campus in campuses:
            events = Event.query.filter_by(campus_id=campus.id).all()
            event_ids = [e.id for e in events]
            if not event_ids:
                results.append(
                    {'campus': campus.name, 'volunteers': 0, 'attended': 0})
                continue
            vol_count = db.session.query(Registration.user_id)\
                .filter(Registration.event_id.in_(event_ids))\
                .distinct().count()
            attended = Attendance.query.filter(
                Attendance.event_id.in_(event_ids),
                Attendance.status == 'present').count()
            results.append({
                'campus': campus.name,
                'volunteers': vol_count,
                'attended': attended,
            })
        results.sort(key=lambda x: x['attended'], reverse=True)
        return results

    @staticmethod
    def kpi_summary(campus_id=None):
        """Return dict of top-level KPIs, optionally scoped to one campus."""
        user_query = User.query.filter(
            User.role == 'volunteer', User._is_active == True)
        if campus_id:
            user_query = user_query.filter(User.campus_id == campus_id)
        total_active = user_query.count()

        if campus_id:
            event_ids = [e.id for e in Event.query.filter_by(
                campus_id=campus_id).all()]
            reg_q = Registration.query.filter(Registration.event_id.in_(
                event_ids)) if event_ids else Registration.query.filter(False)
        else:
            reg_q = Registration.query

        total_regs = reg_q.count()
        completed_regs = reg_q.filter(
            Registration.status.in_(['confirmed', 'completed'])).count()
        retention_rate = round(
            (completed_regs / total_regs * 100), 1) if total_regs > 0 else 0

        return {
            'total_active_volunteers': total_active,
            'retention_rate': retention_rate,
        }

    @staticmethod
    def trend_data(months=6, campus_id=None):
        """Return monthly attendance and registration counts."""
        cutoff = datetime.now() - timedelta(days=30 * months)

        attended_query = db.session.query(Event.date)\
            .join(Attendance, Attendance.event_id == Event.id)\
            .filter(Event.date >= cutoff)
        reg_query = db.session.query(Event.date)\
            .join(Registration, Registration.event_id == Event.id)\
            .filter(Event.date >= cutoff)

        if campus_id:
            attended_query = attended_query.filter(Event.campus_id == campus_id)
            reg_query = reg_query.filter(Event.campus_id == campus_id)

        attended_rows = attended_query.all()
        reg_rows = reg_query.all()

        attended_map = {}
        for (event_date,) in attended_rows:
            key = event_date.strftime('%Y-%m')
            attended_map[key] = attended_map.get(key, 0) + 1

        reg_map = {}
        for (event_date,) in reg_rows:
            key = event_date.strftime('%Y-%m')
            reg_map[key] = reg_map.get(key, 0) + 1

        all_months = sorted(set(list(reg_map.keys()) + list(attended_map.keys())))
        return {
            'months': all_months,
            'attended': [int(attended_map.get(m, 0)) for m in all_months],
            'registrations': [int(reg_map.get(m, 0)) for m in all_months],
        }

    @staticmethod
    def _event_attendance_counts(events):
        event_ids = [event.id for event in events]
        registrations = dict(db.session.query(
            Registration.event_id, db.func.count(Registration.id)).filter(
            Registration.event_id.in_(event_ids)).group_by(Registration.event_id).all())
        attendance = dict(db.session.query(
            Attendance.event_id, db.func.count(Attendance.id)).filter(
            Attendance.event_id.in_(event_ids), Attendance.status == 'present'
        ).group_by(Attendance.event_id).all())
        return registrations, attendance

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

    # ── Phase 18: centralized descriptive analytics ────────────────────────────
    #
    # Metric definitions (shared with build_events_report so dashboard, CSV and
    # PDF never disagree for the same scope/filters):
    #
    #   Registrations          = count(valid registrations) where status != 'cancelled'
    #   PSU Registrations      = registrations linked to a User (role=volunteer)
    #   External Registrations = registrations linked to an ExternalParticipant
    #   Unique Volunteers      = COUNT(DISTINCT Registration.user_id)
    #   Attended               = COUNT(Attendance.status == 'present')
    #   Attendance Rate        = Attended / Registrations * 100   (0 if no registrations)
    #   Conversion Rate        = Attended / Registrations * 100   (sign-up→attendance)
    #
    # Coordinators must always pass their own campus_id; this module never reads
    # a client-supplied campus id, so cross-campus leakage is impossible.

    @staticmethod
    def _scoped_event_query(campus_id=None, start_date=None, end_date=None,
                            category=None):
        """Return a base Event query honouring campus/date/category scope."""
        from datetime import timedelta
        q = Event.query
        if campus_id:
            q = q.filter(Event.campus_id == campus_id)
        if start_date:
            try:
                s = datetime.strptime(start_date, '%Y-%m-%d')
                q = q.filter(Event.date >= s)
            except (ValueError, TypeError):
                pass
        if end_date:
            try:
                e = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                q = q.filter(Event.date < e)
            except (ValueError, TypeError):
                pass
        if category:
            q = q.filter(Event.category == category)
        return q

    @staticmethod
    def participation_summary(campus_id=None, start_date=None, end_date=None,
                              category=None):
        """Central KPI bundle for a scope. Derives from build_events_report so
        the numbers always match the CSV/PDF exports for the same filters."""
        rows, summary = build_events_report(
            campus_id=campus_id, start_date=start_date, end_date=end_date,
            category=category)
        event_ids = [e.id for e in AnalyticsAggregator._scoped_event_query(
            campus_id, start_date, end_date, category).all()]
        unique = (db.session.query(db.func.count(db.distinct(
            Registration.user_id))).filter(
                Registration.event_id.in_(event_ids),
                Registration.user_id.isnot(None)).scalar() or 0
            ) if event_ids else 0

        regs = summary['total_registrations']
        attended = summary['total_attended']
        safe_div = (attended / regs * 100) if regs > 0 else 0.0
        return {
            'event_count': summary['event_count'],
            'registrations': regs,
            'psu_registrations': summary['total_psu'],
            'external_registrations': summary['total_external'],
            'unique_volunteers': int(unique),
            'attended': attended,
            'completed': summary['total_completed'],
            'attendance_rate': round(safe_div, 1),
            'conversion_rate': round(safe_div, 1),
        }

    @staticmethod
    def campus_comparison():
        """Cross-campus comparison rows (Director/Admin only). One row per
        campus with registrations, unique volunteers, attended, and rate."""
        results = []
        for c in Campus.query.order_by(Campus.name).all():
            s = AnalyticsAggregator.participation_summary(campus_id=c.id)
            results.append({
                'campus': c.name,
                'campus_id': c.id,
                'registrations': s['registrations'],
                'unique_volunteers': s['unique_volunteers'],
                'attended': s['attended'],
                'attendance_rate': s['attendance_rate'],
            })
        results.sort(key=lambda r: r['registrations'], reverse=True)
        return results

    @staticmethod
    def activity_performance(campus_id=None, start_date=None, end_date=None,
                             category=None, limit=10):
        """Per-activity performance: registrations, attended, conversion."""
        rows, _ = build_events_report(
            campus_id=campus_id, start_date=start_date, end_date=end_date,
            category=category)
        out = []
        for r in rows:
            regs = r['registrations']
            conv = round(r['attended'] / regs * 100, 1) if regs > 0 else 0.0
            out.append({
                'event_id': r['event_id'], 'title': r['title'],
                'date': r['date'], 'category': r['category'],
                'campus': r['campus'], 'registrations': regs,
                'attended': r['attended'], 'conversion_rate': conv,
                'completed': r['completed'],
            })
        out.sort(key=lambda x: x['registrations'], reverse=True)
        return out[:limit]

    @staticmethod
    def activity_accomplishments(campus_id=None, start_date=None, end_date=None,
                                 category=None, limit=20):
        """Live-event goals; verified attendance is the only actual count."""
        rows = []
        for event in AnalyticsAggregator._scoped_event_query(
                campus_id, start_date, end_date, category).order_by(Event.date.desc()).all():
            registrations = Registration.query.filter(
                Registration.event_id == event.id,
                Registration.status != 'cancelled').count()
            actual = Attendance.query.filter_by(
                event_id=event.id, status='present').count()
            cancelled = Registration.query.filter_by(
                event_id=event.id, status='cancelled').count()
            target = event.target_participants
            rows.append({
                'event': event, 'registrations': registrations, 'actual': actual,
                'cancelled': cancelled, 'target': target,
                'completion_percentage': round(actual / target * 100, 1)
                if target else None,
            })
        return rows[:limit]

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
    def category_distribution(campus_id=None, start_date=None, end_date=None):
        """Participation grouped by existing event category."""
        rows, _ = build_events_report(
            campus_id=campus_id, start_date=start_date, end_date=end_date)
        cats = {}
        for r in rows:
            cat = r['category'] or 'General'
            bucket = cats.setdefault(cat, {'registrations': 0, 'attended': 0})
            bucket['registrations'] += r['registrations']
            bucket['attended'] += r['attended']
        return [{'category': k, 'registrations': v['registrations'],
                 'attended': v['attended']}
                for k, v in sorted(
                    cats.items(), key=lambda kv: kv[1]['registrations'],
                    reverse=True)]

    @staticmethod
    def psu_vs_outsider(campus_id=None, start_date=None, end_date=None,
                        category=None):
        """PSU (User) vs Outsider (ExternalParticipant) registration split."""
        _, summary = build_events_report(
            campus_id=campus_id, start_date=start_date, end_date=end_date,
            category=category)
        return {'psu': summary['total_psu'],
                'outsider': summary['total_external']}

    @staticmethod
    def monthly_engagement(campus_id=None, months=12):
        """Chronologically ordered monthly registration/attendance counts.
        Python aggregation keeps the query DB-agnostic (sqlite + MariaDB)."""
        events = AnalyticsAggregator._scoped_event_query(campus_id).all()
        reg_map, att_map = {}, {}
        for e in events:
            regs = Registration.query.filter(
                Registration.event_id == e.id,
                Registration.status != 'cancelled').count()
            att = Attendance.query.filter_by(
                event_id=e.id, status='present').count()
            key = e.date.strftime('%Y-%m')
            reg_map[key] = reg_map.get(key, 0) + regs
            att_map[key] = att_map.get(key, 0) + att
        rows = [
            {'period': period, 'registrations': reg_map.get(period, 0),
             'attended': att_map.get(period, 0)}
            for period in sorted(set(reg_map) | set(att_map))
        ][-months:]
        return {
            'months': [row['period'] for row in rows],
            'registrations': [int(row['registrations']) for row in rows],
            'attended': [int(row['attended']) for row in rows],
        }

    @staticmethod
    def weekly_engagement(campus_id=None, weeks=12):
        """Chronologically ordered weekly registration/attendance counts."""
        events = AnalyticsAggregator._scoped_event_query(campus_id).all()
        reg_map, att_map = {}, {}
        for e in events:
            regs = Registration.query.filter(
                Registration.event_id == e.id,
                Registration.status != 'cancelled').count()
            att = Attendance.query.filter_by(
                event_id=e.id, status='present').count()
            y, w, _ = e.date.isocalendar()
            key = f'{y}-W{w:02d}'
            reg_map[key] = reg_map.get(key, 0) + regs
            att_map[key] = att_map.get(key, 0) + att
        weeks_list = sorted(set(reg_map) | set(att_map))
        if len(weeks_list) > weeks:
            weeks_list = weeks_list[-weeks:]
        return {
            'weeks': weeks_list,
            'registrations': [reg_map.get(wk, 0) for wk in weeks_list],
            'attended': [att_map.get(wk, 0) for wk in weeks_list],
        }

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
        volunteers = db.session.query(
            User.id, User.name, Campus.name,
            db.func.count(Attendance.id).label('attendance')
        ).join(Attendance, Attendance.user_id == User.id).join(
            Event, Event.id == Attendance.event_id).outerjoin(
            Campus, Campus.id == User.campus_id).filter(
                User.role == 'volunteer', Attendance.status == 'present',
                Event.date >= start, Event.date < end).group_by(
                    User.id, User.name, Campus.name).all()
        completed_counts = dict(db.session.query(
            Registration.user_id, db.func.count(Registration.id)).join(Event).filter(
            Registration.status == 'completed', Event.date >= start, Event.date < end
        ).group_by(Registration.user_id).all())
        volunteer_rows = []
        for user_id, name, campus, attendance in volunteers:
            completed = completed_counts.get(user_id, 0)
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
        for campus in Campus.query.order_by(Campus.name).all():
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

    @staticmethod
    def heatmap_data():
        """Return attendance counts for campus engagement heatmap."""
        campuses = Campus.query.all()
        data = []
        for campus in campuses:
            events = Event.query.filter_by(campus_id=campus.id).all()
            event_ids = [e.id for e in events]
            if not event_ids:
                data.append({'campus': campus.name, 'value': 0.0})
                continue
            attended = Attendance.query.filter(
                Attendance.event_id.in_(event_ids),
                Attendance.status == 'present').count()
            data.append({'campus': campus.name, 'value': attended})
        return data

    @staticmethod
    def forecast_turnout(campus_id=None):
        """
        Predict expected attendance rate for upcoming events using linear
        regression trained on past events' slots vs. actual attendance rate.

        Returns list of {event, predicted_attendance_rate}.
        """
        past_query = Event.query.filter(Event.date < datetime.now())
        if campus_id:
            past_query = past_query.filter(Event.campus_id == campus_id)
        past_events = past_query.all()
        registrations, attendance = AnalyticsAggregator._event_attendance_counts(past_events)

        X_train, y_train = [], []
        for e in past_events:
            total_regs = registrations.get(e.id, 0)
            attended = attendance.get(e.id, 0)
            if total_regs > 0:
                X_train.append([e.slots])
                y_train.append(attended / total_regs)

        # Need at least a handful of past events to fit a meaningful line (Ang Problem natin***)
        if len(X_train) < 3:
            return []

        model = LinearRegression().fit(np.array(X_train), np.array(y_train))

        upcoming_query = Event.query.filter(Event.date >= datetime.now())
        if campus_id:
            upcoming_query = upcoming_query.filter(
                Event.campus_id == campus_id)

        results = []
        for e in upcoming_query.all():
            predicted = float(model.predict([[e.slots]])[0])
            predicted = min(max(predicted, 0.0), 1.0)
            results.append({
                'event': e,
                'predicted_attendance_rate': round(predicted, 3),
            })
        return results

