# Phase 3 Wave 2 — Requisition, Corrigendum, Doc Verification

**Date**: 2026-08-08 · **Status**: Approved design · **Source**: roadmap §3.1, §3.4, §3.5

---

## 3.1 Vacancy Requisition → Approval Workflow

**Problem**: no requisition/approval flow before advertisement creation.

**Build**:
- Models `VacancyRequisition` (recruitment): post_name CharField, count PositiveInteger, grade CharField, justification TextField, status draft/submitted/finance_approved/reservation_certified/ca_approved/rejected, created_by FK null, created_at. `RequisitionApproval` (FK requisition, stage CharField, approver FK null, decision approved/rejected, comments, timestamp).
- View: `requisition_list` (hr_manager GET), `requisition_create` (hr_manager POST), `requisition_detail` (shows approvals), `requisition_approve` (role-gated per stage: finance→finance_officer, reservation→hr_manager, ca→org_admin; requires comments on rejection).
- Status flow: draft → submitted → finance_approved → reservation_certified → ca_approved → advertisement can be created (link via ForeignKey on Advertisement? Or just status-check gate on `advertisement_create` — simpler: when ca_approved, allow the create form to pre-fill from the requisition).
- Audit: each approval/rejection → `log_audit`.

## 3.4 Corrigendum Module

**Problem**: no way to amend published advertisements.

**Build**:
- Model `Corrigendum` (recruitment): advertisement FK, version PositiveIntegerField, changes_text TextField, published_date DateField, is_active Bool default True, created_at. Unique on (advertisement, version).
- View: `corrigendum_create` (hr_manager POST, same URL as advertisement detail), `corrigendum_list` on advt detail page (read by all). On create: bump version, record changes, optionally auto-notify all applicants via the notification system (`notify(channel="portal", to=<each applicant>, subject="Corrigendum...", body=changes_text)`).
- Template: advertisement_detail.html shows a "Corrigenda" section at the bottom listing all corrigenda; "Add Corrigendum" button (hr_manager only).

## 3.5 Document Verification Workflow

**Problem**: `Document.is_verified` is a single checkbox; no structured verification flow.

**Build**:
- Model `DocumentVerification` (recruitment): document FK OneToOne, verifier FK null, status pending/verified/rejected, comments TextField, verified_at null, created_at.
- View: `verify_documents` (recruiter GET lists unverified docs for an application, POST approves/rejects with comments). `document_verification_dashboard` (recruiter: workload stats — pending count, avg verification time).
- Wire: auto-create `DocumentVerification(pending)` when a Document is created (signal or in the apply flow). Audit on status change.
- Status change restrictions: only the assigned verifier (or hr_manager) can change status.

## Commands
`pytest -q` · E2E · `migrate_schemas` · commits per item
