"""
Recommendation Engine for PSU Volunteer Hub
============================================
Content-based recommendation using cosine similarity between a
volunteer's skill/interest terms and each event's skill/category terms.

This engine uses scikit-learn cosine similarity over *binary* term vectors.
It does not use TF-IDF weighting; term presence, not frequency, is measured.

Terms are represented as binary vectors over their combined, normalized,
synonym-collapsed vocabulary.
Cosine similarity = |shared terms| / sqrt(|user terms| * |event terms|)
"""
import re
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import selectinload, joinedload, load_only
from sqlalchemy import insert
from app.models.event import Event, RecommendationLog, Registration
from app.models.user import User, Skill, Interest
from app.models import db


# Shared lookup for volunteer and event terms: known short forms match full names.
# Only listed aliases change; this is not fuzzy matching or language understanding.
SYNONYM_MAP = {
    'cs': 'computer skills',
    'ict': 'it/computer skills',
    'it': 'it/computer skills',
    'tech': 'technology',
    'env': 'environmental conservation',
    'environment': 'environmental conservation',
    'teach': 'teaching',
    'teaching/tutoring': 'teaching',
    'medical': 'medical/first aid',
    'first aid': 'medical/first aid',
    'comm': 'communication',
    'communication/public speaking': 'communication',
    'agri': 'agriculture',
    'agriculture/farming': 'agriculture',
}


def _normalize_token(term):
    """Clean one term so spelling format does not block matching.

    Trim edges, lowercase, remove trailing periods/commas/semicolons, and
    collapse repeated spaces. Replace known aliases through SYNONYM_MAP.
    Return None for empty input; keep unknown terms as cleaned text.
    """
    if not term:
        return None
    token = term.strip().lower()
    token = re.sub(r'[.,;]+$', '', token)
    token = re.sub(r'\s+', ' ', token).strip()
    if not token:
        return None
    return SYNONYM_MAP.get(token, token)


def normalize_terms(raw_terms):
    """Clean each supplied term, discard blanks, and remove duplicates.

    Return a set: choosing the same term twice gives no extra score.
    Expect a collection of whole terms, not a single comma-separated string.
    """
    result = set()
    if not raw_terms:
        return result
    for term in raw_terms:
        token = _normalize_token(term)
        if token:
            result.add(token)
    return result


def _cosine_similarity(user_terms: set, event_terms: set) -> float:
    """Measure shared terms using binary cosine similarity, from 0 to 1.

    Clean both sets. Build one shared vocabulary; mark each term 1 when
    present, 0 when absent. scikit-learn compares those two vectors.
    Formula: shared_term_count / sqrt(user_term_count * event_term_count).
    Example: {teaching, health} versus {teaching} gives about 0.7071.
    Empty side gives 0. No trained model, TF-IDF, or word-frequency weighting.
    """
    user_terms = normalize_terms(user_terms)
    event_terms = normalize_terms(event_terms)
    if not user_terms or not event_terms:
        return 0.0
    vocabulary = sorted(user_terms | event_terms)
    user_vector = [[1 if term in user_terms else 0 for term in vocabulary]]
    event_vector = [[1 if term in event_terms else 0 for term in vocabulary]]
    return float(cosine_similarity(user_vector, event_vector)[0][0])


def get_recommendations(volunteer_profile, events=None, top_n=5, campus_id=None, commit=True):
    """Rank activity fit from profile terms and registration history.

    Combine profile skills/interests into one set. Compare against each
    event's required skills plus category, then add 0.15 for a previously
    joined category, capped at 1. Cancelled/rejected history gives no boost.
    Joining a category needs a registration, not verified attendance.

    Exclude events already registered for, except cancelled/rejected entries.
    With events=None, query upcoming events across campuses. Supplied events
    keep caller's date, campus, and eligibility scope; only registration
    exclusion happens here. No capacity or positive-score cutoff applies.
    Missing profile, empty selections, or missing user uses fallback instead.

    Return at most top_n rows with event, score (4 decimal places), matching
    profile skill/interest sets, and percentage. Percentage is rounded score
    * 100, not attendance probability. Equal scores keep candidate order.
    Save top results through _log_recommendations; commit=False leaves
    transaction control to caller. Fallback returns without saving logs.
    campus_id affects only fallback's own query, not personalized scoring.
    """
    if volunteer_profile is None or (not volunteer_profile.skill_list and not volunteer_profile.interest_list):
        return _cold_start_recommendations(events, top_n, campus_id=campus_id)

    user = db.session.get(User, volunteer_profile.user_id)
    if user is None:
        return _cold_start_recommendations(events, top_n, campus_id=campus_id)

    user_skills = normalize_terms(volunteer_profile.skill_list)
    user_interests = normalize_terms(volunteer_profile.interest_list)
    user_terms = user_skills | user_interests

    history = db.session.query(Registration.event_id, Registration.status, Event.category).outerjoin(
        Event, Event.id == Registration.event_id).filter(Registration.user_id == user.id).all()
    registered_ids = {event_id for event_id, status, _ in history
                      if status not in ('cancelled', 'rejected')}

    # Registration history supplies category preference; attendance is not required.
    history_categories = set()
    for _, status, category in history:
        if status in ('cancelled', 'rejected'):
            continue
        if category:
            history_categories |= normalize_terms([category])

    if events is not None:
        candidates = [e for e in events if e.id not in registered_ids]
    else:
        candidates = Event.query.filter(
            db.not_(Event.id.in_(registered_ids))
        ).filter(Event.date >= datetime.now()).options(selectinload(Event.required_skills_rel),
            load_only(Event.id, Event.date, Event.category)).order_by(Event.date.asc(), Event.id).all()

    scored = []
    similarities = {}
    for event in candidates:
        event_skills = normalize_terms(s.name for s in event.required_skills_rel)
        event_terms = set(event_skills)
        if event.category:
            event_terms |= normalize_terms([event.category])

        terms_key = frozenset(event_terms)
        # Same term set means same base score; reuse within this request.
        if terms_key not in similarities:
            similarities[terms_key] = _cosine_similarity(user_terms, event_terms)
        score = similarities[terms_key]
        matched = user_terms & event_terms

        # Fixed bonus applies once per matching category, regardless of join count.
        if event.category and (normalize_terms([event.category]) & history_categories):
            score = min(1.0, score + 0.15)

        scored.append({
            'event': event,
            'score': round(score, 4),
            'matched_skills': matched & user_skills,
            'matched_interests': matched & user_interests,
            'percentage': min(round(score * 100), 100),
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    top = scored[:top_n]
    if top:
        Event.query.filter(Event.id.in_([item['event'].id for item in top])).options(
            joinedload(Event.campus)).populate_existing().all()
    _log_recommendations(user, top, commit=commit)
    return top


def _cold_start_recommendations(events=None, limit=5, campus_id=None):
    """Suggest popular activities when profile cannot produce a personal match.

    With events=None, query upcoming events and restrict to campus_id when
    supplied. With a supplied list, trust caller's scope; no extra campus,
    date, capacity, or existing-registration filter applies here.
    Count every registration, including cancelled/rejected rows. More
    registrations rank first; earlier event dates break popularity ties.
    Return at most limit events with score/percentage 0 and empty match sets.
    Zero means no personal score calculated, not proof of unsuitable activity.
    Fallback does not write RecommendationLog records.
    """
    if events is None:
        query = Event.query.filter(Event.date >= datetime.now())
        if campus_id:
            query = query.filter(Event.campus_id == campus_id)
        events = query.all()

    reg_counts = dict(
        db.session.query(Registration.event_id, db.func.count(Registration.id))
        .filter(Registration.event_id.in_([event.id for event in events])).group_by(Registration.event_id).all()
    )

    events = sorted(
        events,
        key=lambda e: (reg_counts.get(e.id, 0), e.date.timestamp() * -1),
        reverse=True,
    )
    top = events[:limit]
    if top:
        Event.query.filter(Event.id.in_([event.id for event in top])).options(
            joinedload(Event.campus)).populate_existing().all()
    return [{
        'event': e,
        'score': 0,
        'matched_skills': set(),
        'matched_interests': set(),
        'percentage': 0,
    } for e in top]


def bootstrap_from_event(user, event, top_skills=3, commit=True):
    """Fill an empty profile from a registered event for future matching.

    Stop if user already has any skills or interests. Otherwise copy up to
    top_skills required-skill entries (default 3) in relationship order and
    use event category as an interest. Reuse matching taxonomy records or
    create missing ones. These inferred choices do not verify proficiency.
    commit=True saves changes; False lets registration caller save everything
    in one transaction. This function checks empty selections, not join count.
    """
    if user.skills or user.interests:
        return

    for name in [s.name for s in event.required_skills_rel][:top_skills]:
        skill = Skill.query.filter_by(name=name).first() or Skill(name=name)
        db.session.add(skill)
        user.skills.append(skill)

    if event.category:
        interest = Interest.query.filter_by(
            name=event.category).first() or Interest(name=event.category)
        db.session.add(interest)
        user.interests.append(interest)

    if commit:
        db.session.commit()


def _log_recommendations(user, recommendations, commit=True):
    """Save one RecommendationLog row per returned personalized suggestion.

    Bulk-insert user ID, event ID, and final score, including history bonus.
    Repeated calls can add new rows for the same user/event; no deduplication.
    commit=True commits the current session, including other pending changes;
    False leaves saving or rollback to caller. Empty input inserts no rows.
    """
    if recommendations:
        db.session.execute(insert(RecommendationLog), [dict(user_id=user.id,
            event_id=rec['event'].id, similarity_score=rec['score']) for rec in recommendations])
    if commit:
        db.session.commit()
