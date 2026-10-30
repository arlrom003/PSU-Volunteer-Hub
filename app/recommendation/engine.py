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
from sqlalchemy.orm import selectinload
from app.models.event import Event, RecommendationLog, Registration
from app.models.user import User, Skill, Interest
from app.models import db


# Curated synonym/abbreviation map so variant spellings of taxonomy terms
# collapse to a single canonical token. Applied identically to both user and
# event terms so matches are preserved (or improved) rather than lost.
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
    """Lowercase, trim, strip trailing punctuation, and apply synonyms."""
    if not term:
        return None
    token = term.strip().lower()
    token = re.sub(r'[.,;]+$', '', token)
    token = re.sub(r'\s+', ' ', token).strip()
    if not token:
        return None
    return SYNONYM_MAP.get(token, token)


def normalize_terms(raw_terms):
    """Return a canonicalized set of taxonomy terms (deduplicated)."""
    result = set()
    if not raw_terms:
        return result
    for term in raw_terms:
        token = _normalize_token(term)
        if token:
            result.add(token)
    return result


def _cosine_similarity(user_terms: set, event_terms: set) -> float:
    """Return cosine similarity for two binary term vectors."""
    user_terms = normalize_terms(user_terms)
    event_terms = normalize_terms(event_terms)
    if not user_terms or not event_terms:
        return 0.0
    vocabulary = sorted(user_terms | event_terms)
    user_vector = [[1 if term in user_terms else 0 for term in vocabulary]]
    event_vector = [[1 if term in event_terms else 0 for term in vocabulary]]
    return float(cosine_similarity(user_vector, event_vector)[0][0])


def get_recommendations(volunteer_profile, events=None, top_n=5, campus_id=None):
    """
    Score events for a volunteer using cosine similarity over
    combined skill + interest/category terms.

    Parameters:
      volunteer_profile : VolunteerProfile (or None for cold-start)
      events            : optional pre-filtered list of Event rows
      top_n             : number of recommendations to return
      campus_id         : campus used by the cold-start fallback

    Returns list of dicts: [{event, score, matched_skills, matched_interests, percentage}]
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

    # Participation history: categories the volunteer has actually joined weigh
    # toward future events of the same category (cold-start-safe: empty if none).
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
        ).filter(Event.date >= datetime.now()).options(selectinload(Event.required_skills_rel)
        ).order_by(Event.date.asc()).limit(50).all()

    scored = []
    for event in candidates:
        event_skills = normalize_terms(s.name for s in event.required_skills_rel)
        event_terms = set(event_skills)
        if event.category:
            event_terms |= normalize_terms([event.category])

        score = _cosine_similarity(user_terms, event_terms)
        matched = user_terms & event_terms

        # Participation-history weighting: a small, capped boost when this event's
        # category matches a category the volunteer has previously joined.
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
    _log_recommendations(user, top)
    return top


def _cold_start_recommendations(events=None, limit=5, campus_id=None):
    """
    Fallback when no profile, skills, or interests exist.
    Ranks upcoming events by popularity (registration count), preferring
    the volunteer's campus, with soonest events breaking ties.
    """
    if events is None:
        query = Event.query.filter(Event.date >= datetime.now())
        if campus_id:
            query = query.filter(Event.campus_id == campus_id)
        events = query.all()

    reg_counts = dict(
        db.session.query(Registration.event_id, db.func.count(Registration.id))
        .group_by(Registration.event_id).all()
    )

    events = sorted(
        events,
        key=lambda e: (reg_counts.get(e.id, 0), e.date.timestamp() * -1),
        reverse=True,
    )
    return [{
        'event': e,
        'score': 0,
        'matched_skills': set(),
        'matched_interests': set(),
        'percentage': 0,
    } for e in events[:limit]]


def bootstrap_from_event(user, event, top_skills=3):
    """
    Seed a cold-start volunteer's skills/interests from their first
    registered event, so future recommendations become personalized.
    No-op once the user already has any skills or interests.
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

    db.session.commit()


def _log_recommendations(user, recommendations):
    """Persist recommendation results for analysis."""
    for rec in recommendations:
        log = RecommendationLog(
            user_id=user.id,
            event_id=rec['event'].id,
            similarity_score=rec['score'],
        )
        db.session.add(log)
    db.session.commit()
