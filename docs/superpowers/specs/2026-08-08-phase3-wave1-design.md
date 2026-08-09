# Phase 3 Wave 1 — Roster Register, Fee Payment, Notifications

**Date**: 2026-08-08 · **Status**: Approved design (Wave 1 of Phase 3) · **Source**: roadmap §3.2, §3.3, §3.6

All three are standalone ([S]) per the roadmap. External integrations (payment gateway, email/SMS providers) are built behind adapters with mocks, per the approved "everything, roadmap order" strategy — the credential-gated live calls are documented TODOs.

---

## 3.2 Post-Based Roster Register (DoPT 100-Point)

**Problem**: `RosterMatrix` is per-post/per-cycle; no persistent DoPT 100-point roster that survives recruitment cycles.

**Build**:
- New `PostBasedRoster` model (recruitment, tenant schema): `post` FK unique, `cycle_start_year` Integer, `roster_points` JSON (list of entries `{serial, category, point_type: "l"|"r"|"u"}`), `current_position` PositiveInteger default 1, `liaison_officer` FK AUTH_USER null, `certified_on`/`certified_by` for liaison certification, `created_at`.
- Generator `build_roster(post, start_year, include_pwbd=False) -> list[entry]`: DoPT 100-point pattern with the standard cycle order (UR/LR/SC/R/ST/LR/UR/UR/UR/R/OBC/LR/UR/UR/UR/R/EWS/UR/UR/UR/R…). Deterministic pure function in `recruitment/roster.py` (unit-testable without DB).
- Consumption: `roster_view` gains a "Generate DoPT roster" action that builds/stores the roster from `post.category_breakup`-aware counts; admin + read view render the 100-point grid with `current_position` highlighted; when an offer consumes a slot (offer → `joined`), `current_position` advances (wired in the offer acceptance path via a signal on Application status→joined, or explicit call in accept_offer — prefer the signal `post_save Application` when status changed to joined: advance `PostBasedRoster.current_position` for the application's post).
- UI: staff `roster_view` shows the persistent roster grid (per post) + certification fields; `RosterMatrix` (per-cycle) stays for the existing breach warnings.

## 3.3 Fee Payment + Exemption Engine

**Problem**: boilerplate promises fee payment; nothing implements it.

**Build**:
- **Exemption engine** (pure, `recruitment/fees.py`): `fee_exempt(candidate, post) -> (bool, reason)` — exempt iff category in {"sc","st"} OR `profile.is_pwbd` OR gender == "F"; special case: SC/ST candidates applying to UR posts pay (per boilerplate). `fee_amount(post) -> str` from `post.category_breakup`-derived rules (Rs 500/- default; amount field on Post optional `fee_amount` Decimal null → default 500).
- **Payment adapter** (`recruitment/payments.py`): `PaymentGateway` protocol with `create_payment(order, amount, candidate) -> dict {id, url}` and `verify(payload) -> bool`; `MockPaymentGateway` (immediate success, deterministic id) + `RazorpayGateway` stub raising `NotConfigured` unless `RAZORPAY_KEY_ID/SECRET` set. Env-driven `PAYMENT_GATEWAY=mock|razorpay`.
- **Models**: `Payment` (recruitment): application FK OneToOne, amount Decimal, gateway CharField, gateway_ref CharField blank, status CharField (pending/paid/failed/refunded), paid_at, created_at. Wire: portal apply success → auto-create Payment(pending, amount from fee engine) + record exemption reason on the application (`fee_exempted` JSON on Application? No new Application fields — store exemption in the Payment row: `exempt` bool + `exempt_reason`).
- **UI**: slip PDF fee line + portal application_detail "Pay Application Fee" button (mock gateway marks paid immediately; razorpay stub raises → friendly error). Reconciliation view for staff: `fee_reconciliation` (recruitment views) — count by status/exemption, CSV export.
- **Audit**: payment status changes → `log_audit(..., "payment", old, new, reason)`.

## 3.6 Email/SMS Notifications

**Problem**: zero delivery; OTP prints to console.

**Build**:
- New tenant-app `notifications` (TENANT_APPS): `NotificationOutbox` model (recipient, channel email|sms, subject, body, provider, status queued|sent|failed, error, sent_at, created_at) + `NotificationTemplate` (key, channel, subject_template, body_template) seeded via migration/data with the standard messages (acknowledgement, status update, interview invite, offer, rejection, corrigendum).
- Provider adapter `notifications/providers.py`: `send(channel, to, subject, body) -> (ok, error)`; `ConsoleProvider` (prints, ok) default; `SmtpProvider` (django.core.mail, env SMTP_*); `TwilioSmsProvider` stub (env TWILIO_*; NotConfigured otherwise). Env `NOTIFY_PROVIDER=console|smtp|twilio`.
- Wiring: replace the OTP `print()` in `portal/views.py` register with `notify("sms"|"email", to, template_key="otp", context={otp})` (console provider prints the OTP line — dev behavior preserved); Application post_save → enqueue acknowledgement (when created) via signal; offer acceptance → rejection/offer templates (defer broad signal wiring to Phase 3.6 scope: acknowledgement on create + offer notification on accept are the two wired flows; the rest of the template keys exist for later flows).
- Admin: outbox list (status filter, resend action) — keep minimal (list + resend via admin action).
- Tests: exemption engine cases (SC/ST exempt; SC-to-UR pays; female exempt; PwBD exempt), Payment mock flow (create→paid, slip shows it, reconciliation counts), NotificationOutbox creation on application create + offer accept, console provider writes to stdout capture, OTP still printed.

## Commands
`pytest -q` (full suite green) · E2E · `migrate_schemas` (new models) · commits `Phase 3: Roster — …`, `Phase 3: Fee — …`, `Phase 3: Notify — …`
