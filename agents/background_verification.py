"""Background Verification Agent.

Compiles NEUTRAL facts from authorised/consented sources into a tabulated report.
This agent NEVER produces risk scores or recommendations — candidates get the
right to explain and humans make the final decision.
"""

import datetime


NEUTRAL_STATUSES = (
    ("verified", "Verified"),
    ("clear", "No record found in searched sources"),
    ("pending", "Verification pending"),
    ("disposed", "Disposed / closed"),
    ("inconsistent", "Conflicting or incomplete — explanation required"),
)


def compile_facts(application, digilocker_docs=None, bgv_rows=None, sources=None):
    """Return a neutral tabulated facts dict ready for the BackgroundReport.

    Args:
        application: recruitment.Application
        digilocker_docs: list of dicts (doc_type, issuer, verified) — from DL agent
        bgv_rows: list of dicts with keys category, fact, source, date, status
        sources: dict of {source_name: jurisdictions_covered}
    """
    candidate = application.candidate
    rows = []

    # 1. Identity row (from applicant-declared data — no external call)
    rows.append(
        {
            "category": "Identity",
            "fact": f"Name: {candidate.first_name} {candidate.last_name}; "
                    f"DOB: {candidate.date_of_birth or 'Not declared'}; "
                    f"Contact: {candidate.email}",
            "source": "Application form",
            "date": datetime.date.today().isoformat(),
            "status": "declared",
            "candidate_explanation": "",
            "reviewer_notes": "",
        }
    )

    # 2. DigiLocker rows
    for doc in digilocker_docs or []:
        rows.append(
            {
                "category": doc.get("doc_type", "Document"),
                "fact": f"Document issued by {doc.get('issuer', 'Unknown')} "
                        f"on {doc.get('issue_date', 'Unknown')}",
                "source": "DigiLocker (mock in Phase I)",
                "date": doc.get("issue_date", datetime.date.today().isoformat()),
                "status": "verified" if doc.get("signature_valid", True) else "inconsistent",
                "candidate_explanation": "",
                "reviewer_notes": "",
            }
        )

    # 3. BGV rows (from licensed providers — NEVER web-scraped)
    for row in bgv_rows or []:
        rows.append(
            {
                "category": row.get("category", "Background Check"),
                "fact": row.get("fact", ""),
                "source": row.get("source", "Licensed BGV provider"),
                "date": row.get("date", datetime.date.today().isoformat()),
                "status": row.get("status", "pending"),
                "candidate_explanation": "",
                "reviewer_notes": "",
            }
        )

    return {
        "application_id": application.application_id,
        "candidate": f"{candidate.first_name} {candidate.last_name}",
        "generated_at": datetime.datetime.now().isoformat(),
        "disclaimer": (
            "These are compiled facts only. No automated decision has been made. "
            "Candidate may provide explanation; final assessment rests with an "
            "authorized human reviewer."
        ),
        "sources_queried": sources or {},
        "rows": rows,
    }
