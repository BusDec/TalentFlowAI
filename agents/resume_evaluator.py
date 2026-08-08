"""Resume Evaluator Agent.

Scores a candidate's parsed resume against a post's requirements, producing a
detailed competency matrix (0-100 overall + per-competency scores, positives and
concerns). Falls back to keyword heuristics when no LLM key is configured.
"""

import json
import re

from agents.llm_client import get_llm_client, is_configured, LLMClientError


SYSTEM_PROMPT = (
    "You are an expert recruitment evaluator for an Indian PSU (public sector "
    "enterprise). Evaluate the candidate's parsed resume against the post "
    "requirements. Return ONLY a JSON object with these keys: "
    "overall_score (int 0-100), summary (2-line string), "
    "competencies (array of {name, score(int 0-100), notes}), "
    "positives (array of strings), concerns (array of strings). "
    "Be fair, specific, and reference facts from the resume. No commentary outside JSON."
)


def _extract_json(raw):
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _heuristic_score(resume, post):
    """Deterministic scoring without an LLM — used for demo mode."""
    text = json.dumps(resume).lower() if resume else ""
    req = f"{post.qualification} {post.experience_required}".lower()

    competencies = []
    total = 0
    weights = []

    # Education match
    degree_terms = ["b.tech", "b.e", "m.tech", "bsc", "b.sc", "mbbs", "mba", "llb", "ca", "diploma"]
    edu_score = 0
    for term in degree_terms:
        if term in text:
            edu_score += 20
    edu_score = min(100, edu_score + (30 if "engineering" in req and "engineer" in text else 0))
    competencies.append({"name": "Education Match", "score": edu_score, "notes": "Based on keyword analysis."})
    total += edu_score * 25
    weights.append(25)

    # Experience relevance
    years = 0
    m = re.search(r"total_experience_years[\"']?\s*[:=]\s*(\d+)", text)
    if m:
        years = int(m.group(1))
    exp_score = min(100, years * 15)
    if any(k in text for k in ["hydro", "power", "infrastructure", "construction", "project"]):
        exp_score = min(100, exp_score + 15)
    competencies.append({"name": "Experience Relevance", "score": exp_score, "notes": f"~{years} years detected."})
    total += exp_score * 30
    weights.append(30)

    # Skills alignment
    skills = resume.get("skills", []) if isinstance(resume, dict) else []
    skills_text = " ".join(skills).lower()
    skill_score = min(100, len(skills) * 12)
    for kw in ["sap", "autocad", "ms project", "primavera", "fidic", "excel"]:
        if kw in skills_text or kw in text:
            skill_score = min(100, skill_score + 12)
    competencies.append({"name": "Skills Alignment", "score": skill_score, "notes": f"{len(skills)} skills listed."})
    total += skill_score * 20
    weights.append(20)

    # Career progression
    designation = resume.get("current_designation") if isinstance(resume, dict) else None
    prog_score = 70 if designation else 40
    competencies.append({"name": "Career Progression", "score": prog_score, "notes": designation or "No designation."})
    total += prog_score * 15
    weights.append(15)

    # Sector relevance
    sector_score = 80 if any(k in text for k in ["power", "hydro", "energy", "thermal"]) else 45
    competencies.append({"name": "Sector Relevance", "score": sector_score, "notes": "Power sector keywords detected."})
    total += sector_score * 10
    weights.append(10)

    overall = int(round(total / sum(weights)))
    positives = [c["name"] for c in competencies if c["score"] >= 75]
    concerns = [c["name"] for c in competencies if c["score"] < 55]

    return {
        "overall_score": overall,
        "summary": f"Resume scored {overall}/100 by heuristic evaluator.",
        "competencies": competencies,
        "positives": positives or ["No standout strengths detected."],
        "concerns": concerns or ["No major concerns."],
    }


def evaluate_resume(resume, post):
    """Return evaluation dict: overall_score, summary, competencies, positives, concerns.

    Uses the LLM when configured; otherwise deterministic heuristic scoring.
    """
    if not resume:
        return {
            "overall_score": 0,
            "summary": "No parsed resume data available for evaluation.",
            "competencies": [],
            "positives": [],
            "concerns": ["Resume not parsed."],
        }

    if is_configured():
        try:
            client = get_llm_client()
            req_text = (
                f"Post: {post.name}\nQualification: {post.qualification}\n"
                f"Experience: {post.experience_required}"
            )
            raw = client.complete(
                SYSTEM_PROMPT,
                f"POST REQUIREMENTS:\n{req_text}\n\nCANDIDATE RESUME (parsed):\n{json.dumps(resume)[:8000]}",
                max_tokens=1500,
                temperature=0.2,
            )
            parsed = _extract_json(raw)
            if parsed and isinstance(parsed.get("overall_score"), int):
                parsed["overall_score"] = max(0, min(100, parsed["overall_score"]))
                parsed.setdefault("summary", "")
                parsed.setdefault("competencies", [])
                parsed.setdefault("positives", [])
                parsed.setdefault("concerns", [])
                return parsed
        except LLMClientError:
            pass

    return _heuristic_score(resume, post)
