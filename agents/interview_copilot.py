"""Interview Co-pilot Agent.

Generates suggested interview questions from the job description and candidate
resume gaps. Falls back to JD-derived template questions when no LLM is
configured, so the feature always works in demo mode.
"""

from agents.llm_client import get_llm_client, is_configured, LLMClientError


SYSTEM_PROMPT = (
    "You are an interview panel co-pilot for a PSU (Indian public sector) "
    "recruitment. Generate exactly 5 questions for the candidate: "
    "2 technical, 2 behavioural/leadership, 1 role-specific. Return them as a "
    "numbered list, one per line. No preamble."
)


def generate_questions(post, resume_summary=None):
    """Return a list of suggested interview questions."""
    jd = f"Post: {post.name}\nQualification: {post.qualification}\nExperience: {post.experience_required}"

    if is_configured():
        try:
            client = get_llm_client()
            prompt = f"{jd}\n\nCandidate resume summary:\n{resume_summary or 'No resume parsed'}"
            raw = client.complete(SYSTEM_PROMPT, prompt)
            questions = [q.strip(" -1234567890).") for q in raw.strip().splitlines() if q.strip()]
            if questions:
                return questions[:6]
        except LLMClientError:
            pass

    # Deterministic fallback
    return [
        f"Explain your hands-on experience relevant to '{post.name}'.",
        "Describe a challenge you resolved with limited resources.",
        "How do you ensure safety and compliance in your work?",
        "How do you keep your technical skills current?",
        f"Why are you suited for {post.name} at this organisation?",
    ]
