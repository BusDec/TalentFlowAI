# Task 6: MedicalExam — Complete

## Summary
Implemented the `MedicalExam` model, views, template, migration, admin registration, URL routes, and full test suite.

## Files Changed

### `recruitment/models.py`
- Appended `MedicalExam` model after `Grievance` (Phase 4: Medical Examination section)
- Fields: `application` (FK), `hospital`, `exam_date`, `report_file` (FileField), `fitness_status` (pending/fit/unfit), `notes`, `created_at`, `updated_at`
- `MEDICAL_FITNESS_CHOICES` constant exported for reuse

### `recruitment/migrations/0021_medical_exam.py`
- New migration depending on both `0020_probation_record` and `0020_grievance` (concurrent Phase 4 migrations)

### `recruitment/views.py`
- `medical_schedule` — HR manager schedules exam (GET form, POST creates record)
- `medical_upload_report` — Recruiter uploads report file (POST only)
- `medical_certify` — HR manager certifies fitness as fit/unfit (POST only, with audit)
- Imports updated: `MedicalExam`, `MEDICAL_FITNESS_CHOICES`, `ProbationRecord` (re-ordered alphabetically)

### `recruitment/urls.py`
- `applications/<str:application_id>/medical/schedule/` → `medical_schedule`
- `medical/<int:exam_id>/upload-report/` → `medical_upload_report`
- `medical/<int:exam_id>/certify/` → `medical_certify`

### `templates/recruitment/medical_exam.html`
- Glass-card form with hospital, exam date, and notes fields
- Consistent with existing template patterns (tf-glass, tf-card, tf-field, tf-btn)

### `recruitment/admin.py`
- Registered `MedicalExamAdmin` with list_display, list_filter, search_fields, readonly_fields

### `recruitment/test_medical.py`
- 19 tests covering model creation, `__str__`, defaults, relationships, all 3 views, audit events, role-based access

## Audit
- `medical_certify` calls `log_audit()` on fitness status change with `field_name="medical_fitness"`
- No audit event when status doesn't change

## Test Results
```
19 passed in 207.55s
```
- Model: create, str (pending/fit/unfit), defaults, reverse relationship
- Views: schedule GET/POST, upload report (with file, without file), certify fit/unfit/invalid, no-audit-same-status
- Roles: schedule requires hr_manager, certify requires hr_manager, upload requires recruiter

## Commit
`Phase 4: MedicalExam — workflow + views`
