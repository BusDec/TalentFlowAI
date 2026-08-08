"""Smart Shortlisting Agent.

Ranks candidates for a post by combining AI resume score, parsed skill match,
and eligibility signals. Produces a ranked shortlist for human review — the
agent recommends, humans decide.
"""


def _skills_overlap(resume, required_keywords):
    if not resume or not isinstance(resume, dict):
        return 0
    skills = " ".join(resume.get("skills", []) or []).lower()
    text = str(resume).lower()
    matched = []
    for kw in required_keywords:
        if kw.lower() in skills or kw.lower() in text:
            matched.append(kw)
    return matched


def build_shortlist(applications, required_keywords=None, min_score=0):
    """Return ranked list of dicts for the given applications.

    Args:
        applications: iterable of Application objects (with resume_score + resume_evaluation)
        required_keywords: list of skills/terms to match against parsed resumes
        min_score: minimum resume score to include

    Returns:
        list of {application, resume_score, keyword_matches, match_count,
                 composite_score, rank}
    """
    required_keywords = required_keywords or []
    results = []

    for app in applications:
        score = app.resume_score or 0
        if score < min_score:
            continue

        resume = app.resume_evaluation or {}
        matched = _skills_overlap(resume, required_keywords) or []
        match_count = len(matched)

        # Composite: 70% resume score + 30% skill keyword match (normalised).
        keyword_bonus = min(100, match_count * 20)
        composite = round(0.7 * score + 0.3 * keyword_bonus)

        results.append(
            {
                "application": app,
                "resume_score": score,
                "keyword_matches": matched,
                "match_count": match_count,
                "composite_score": composite,
            }
        )

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    for idx, r in enumerate(results, start=1):
        r["rank"] = idx

    return results
