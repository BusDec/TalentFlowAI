### Task 2: Interview views + auto-schedule — DONE

**Files modified:**
- `recruitment/views.py` — added 4 views: `interview_panel_create` (hr_manager), `interview_schedule` (recruiter), `interview_score`, `interview_results`
- `recruitment/urls.py` — added 4 URL routes
- `recruitment/signals.py` — added auto-schedule signal on Application→interview transition
- `recruitment/test_interview.py` — appended 13 view-level + signal tests
- `templates/recruitment/interview_panel_create.html` — panel creation form
- `recruitment/templates/recruitment/interview_schedule.html` — slot scheduling form
- `templates/recruitment/interview_score.html` — score entry form
- `templates/recruitment/interview_results.html` — aggregate results dashboard

**Verification:** 31/31 tests pass (`pytest recruitment/test_interview.py -x -q --reuse-db`).

**Commit:** `Phase 3: Interview — views + scheduling + score aggregation`
