# Verification Feature Specification

## 1. Overview

Inspection step data (DEFECT_REPORT, DEFECT_FOLLOW_UP) collected by inspectors is often incomplete or incorrect. The existing inspection API is designed for offline batch sync and is unsuitable for interactive review workflows.

**Verification** solves this: a separate online-only workflow where another user reviews defect step data and either approves it or returns it with comments for correction. Only after approval is the corrected data copied back to the original inspection step.

### Goals

- Provide an online-only review/approval workflow for defect inspection steps
- Enforce separation of duties: the verifier cannot be the original inspector
- Support multi-cycle review (submit → reject → fix → resubmit → approve) without snapshot history
- Copy approved data back to the original InspectionStep and bump its `server_modified_at` so offline clients pick up the change on next sync
- Keep the verification aggregate independent from the offline-sync inspection aggregate
- Allow the original inspector to assign and reassign the verifier at any time before approval
- Allow the original inspector to modify verification data fields at any time before approval

### Non-goals

- No offline caching or sync for verification entities
- No copying of EquipmentDefect data (defect stays linked by reference)
- No immutable snapshot history per cycle (single mutable copy updated in place)
- No verification for GENERAL_INSPECTION or DEFECT_UNDECIDED step types
- No DRAFT phase — verification is submitted immediately upon creation with an assigned verifier

---

## 2. Changes to Existing InspectionStep

Two new server-managed columns are added to `lesiv.inspection_step` to reflect verification outcome for the offline-sync client. These fields are **read-only from the client's perspective** — they are set exclusively by the server during copy-back on approval and must not be overwritten by the normal inspection PUT flow.

#### New columns on `lesiv.inspection_step`

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `verified_by` | INTEGER | NULL | Inspector ID of the verifier who approved (cross-aggregate ref, no FK); NULL if not verified |
| `verified_at` | TIMESTAMPTZ | NULL | Timestamp of approval; NULL if not verified  |

**Migration**: Add via a new Flyway migration `ALTER TABLE lesiv.inspection_step ADD COLUMN ...`.

**Pydantic model**: Add  `verified_by: Optional[int] = None`, `verified_at: Optional[datetime] = None` to `InspectionStep` in `app/models/inspection.py`.

**Inspection PUT handling**: These fields are excluded from the client-sent PUT body. The `InspectionRepository` must preserve the existing DB values during upsert (same pattern as `upload_status`/`server_uploaded_at` on Image — server-managed fields are not part of the client contract). The upsert SQL query must not include these columns in the `DO UPDATE SET` clause.

**Copy-back populates these fields**: During approval copy-back (§4), the server sets  `verified_by = current verifier_id`, `verified_at = NOW()` on the source step.

---

## 3. Data Model

### 3.1 New Aggregate: Verification

Verification is a **separate aggregate** with its own tables, repository, router, and SQL queries. It follows all project conventions from AGENTS.md.

#### Table: `lesiv.verification`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Client-generated |
| `inspection_step_id` | UUID NOT NULL | Cross-aggregate ref to `inspection_step.id` (no FK) |
| `plant_id` | UUID NOT NULL | Cross-aggregate ref for access control filtering (no FK) |
| `inspector_id` | INTEGER NOT NULL | Original inspector who created the source step (cross-aggregate ref, no FK) |
| `verifier_id` | INTEGER NOT NULL | Assigned verifier (must have VERIFY access level). Cross-aggregate ref, no FK |
| `status` | `lesiv.verification_status` NOT NULL | Current workflow state |
| `server_modified_at` | TIMESTAMPTZ NOT NULL | Optimistic locking |
| — | — | All InspectionStep fields copied here (see §2.2) |

#### Table: `lesiv.verification_image_link`

| Column | Type | Notes |
|--------|------|-------|
| `verification_id` | UUID NOT NULL PK, FK → `verification(id)` | Parent within aggregate |
| `image_id` | UUID NOT NULL PK | Cross-aggregate ref (no FK) |
| `is_deleted` | BOOLEAN NOT NULL DEFAULT FALSE | Logical deletion |

#### Table: `lesiv.verification_event`

Immutable log of status transitions. Not part of the aggregate sync — append-only.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Server-generated |
| `verification_id` | UUID NOT NULL FK → `verification(id)` | Parent |
| `event_type` | `lesiv.verification_event_type` NOT NULL | SUBMITTED / APPROVED / REJECTED / REASSIGNED |
| `inspector_id` | INTEGER NOT NULL | Who performed the action |
| `comment` | TEXT | Required for REJECTED, optional otherwise |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### 3.2 Copied Fields from InspectionStep

The following fields are copied verbatim from `InspectionStep` into `verification`:

-`step_type`
- `defect_id`, `unit_name`, `description`
- `is_resolved`
- `sticker_type_id`, `t_sticker`, `t_environment`, `t_similar_unit`, `t_observed`, `epsilon`
- `measured_current`, `nominal_current`
- `defect_type_id`
- `is_sticker_present`, `is_test_ready`, `is_attention_required`

Fields **not** copied:
`id` (verification has its own)
`step_status` (not relevant to verification workflow)
`step_number`,  `started_at` - not relevant
`is_verified`, `verified_by`, `verified_at` (server-managed verification outcome fields on the source step)

### 3.3 New Enums

```sql
-- Migration V??__add_verification_enums.sql
CREATE TYPE lesiv.verification_status AS ENUM ('SUBMITTED', 'APPROVED', 'REJECTED');
CREATE TYPE lesiv.verification_event_type AS ENUM ('SUBMITTED', 'APPROVED', 'REJECTED', 'REASSIGNED');
```

### 3.4 Pydantic Models

Following project convention (same model for GET response and PUT body):

- `Verification` — full aggregate with `image_links: list[VerificationImageLink]` and `events: list[VerificationEvent]`
- `VerificationListResponse(items=[...])` — wrapper for list endpoints
- `CreateVerificationRequest(inspection_step_id: UUID, verifier_id: int)` — create action body
- `ReviewVerificationRequest(approved: bool, server_modified_at: datetime, comment: Optional[str])` — approve/reject action body. `server_modified_at` is required and must match the current verification's value; `comment` is required when `approved=False`

---

## 4. API Endpoints

New router: `app/routers/verification.py`, registered in `app/main.py`.

| Method | Path | Description | Access Level |
|--------|------|-------------|--------------|
| POST | `/verification` | Create verification (copy from step, assign verifier, auto-submit) | INSPECT |
| GET | `/verification/by_id/{id}` | Full aggregate with events | READ |
| GET | `/verification/submitted_by_me` | List verifications where current user is the inspector | READ |
| GET | `/verification/assigned_to_me` | List verifications where current user is the verifier | READ |
| PUT | `/verification` | Update verification data and/or reassign verifier | INSPECT |
| POST | `/verification/by_id/{id}/review` | Approve or reject | VERIFY |

### 4.1 POST `/verification` — Create & Submit

**Request body:** `CreateVerificationRequest`

Server-side behavior:
1. Read the source `InspectionStep` + its `ImageLinks` from the inspection aggregate
2. Validate step_type is DEFECT_REPORT or DEFECT_FOLLOW_UP
3. Validate step exists and is not deleted
4. Validate no active (non-APPROVED, non-deleted) verification already exists for this step
5. Validate current user has plant access for the step's plant
6. Validate `verifier_id` refers to an existing inspector with `AccessLevel.VERIFY`
7. Validate `verifier_id != current_user.id` (self-verify prevention)
8. Copy all eligible fields + image links into new Verification aggregate
9. Set `status = SUBMITTED`, `inspector_id = current_user.id`, `verifier_id = request.verifier_id`
10. Append SUBMITTED event
11. Return created Verification

### 4.2 PUT `/verification` — Update Data and/or Reassign Verifier

Only the original inspector (`verification.inspector_id == current_user.id`) may update. Allowed in any non-terminal state (`SUBMITTED`, `REJECTED`). Returns HTTP 400 if `status == APPROVED`.

The PUT body is the full `Verification` model (same as GET response). The client sends the complete aggregate including all copied fields, image links, and `verifier_id`. This single endpoint handles both data edits and verifier reassignment.

Follows standard optimistic locking via `server_modified_at`. Image links are synced using the same add/update/mark-deleted pattern as other aggregates.

Server-side behavior:
1. Validate `current_user.id == verification.inspector_id` (HTTP 403 otherwise)
2. Validate `status != APPROVED` (HTTP 400 otherwise)
3. Standard optimistic locking check on `server_modified_at`
4. If `verifier_id` changed from the current value:
   - Validate new `verifier_id` refers to an existing inspector with `AccessLevel.VERIFY`
   - Validate new `verifier_id != verification.inspector_id` (self-verify prevention)
   - Append REASSIGNED event with `inspector_id = current_user.id`
5. Update all copied fields and sync image links
6. Bump `server_modified_at`
7. Return updated Verification

### 4.3 POST `/verification/by_id/{id}/review`

**Request body:** `ReviewVerificationRequest`

- Validates `request.server_modified_at == verification.server_modified_at`. If they differ, returns HTTP 409 Conflict — the verification was modified since the verifier last read it, and the verifier must re-read before reviewing.
- If `approved=true`: transitions `SUBMITTED` → `APPROVED`, appends APPROVED event, triggers copy-back (§4)
- If `approved=false`: transitions `SUBMITTED` → `REJECTED`, appends REJECTED event with required comment
- Requires `AccessLevel.VERIFY`
- **Verifier check**: rejects if `current_user.id != verification.verifier_id` (HTTP 403) — only the assigned verifier can review

### 4.4 GET `/verification/submitted_by_me`

Returns `VerificationListResponse` containing all verifications where `inspector_id == current_user.id`. Supports `modified_since` filter. Sorted by `server_modified_at DESC`.

### 4.5 GET `/verification/assigned_to_me`

Returns `VerificationListResponse` containing all verifications where `verifier_id == current_user.id`. Supports `modified_since` filter. Sorted by `server_modified_at DESC`.

---

## 4. Copy-Back on Approval

When a verification is approved:

1. Within the same transaction:
   - Overwrite the source `InspectionStep` fields with the verification's copied fields
   - Sync `ImageLinks` on the source step: add new, update existing, mark deleted those absent from verification
   - Set `inspection_step.is_verified = TRUE`, `verified_by = verification.verifier_id`, `verified_at = NOW()`
   - Bump `inspection.server_modified_at` to `NOW()` so offline clients detect the change
2. The verification record remains with `status = APPROVED` (not deleted) for audit purposes

---

## 5. Authorization Rules

| Action | Required Access Level | Additional Checks |
|--------|----------------------|-------------------|
| Create verification | INSPECT | Plant access; verifier has VERIFY level; verifier != creator |
| Read verification | READ | Plant access |
| Update verification (PUT) | INSPECT | `current_user.id == verification.inspector_id` AND `status != APPROVED` |
| Review (approve/reject) | VERIFY | `current_user.id == verification.verifier_id`; `server_modified_at` must match |
| List submitted_by_me | READ | Scoped to `current_user.id` automatically |
| List assigned_to_me | READ | Scoped to `current_user.id` automatically |

Plant access is checked via the existing `permission_service` + `inspector_plant_access` table, using the `plant_id` stored on the verification. For list endpoints, each item is filtered by plant access.

---

## 6. State Machine

```
         ┌───────────┐
    ┌───►│ SUBMITTED │◄──────────────┐
    │    └─────┬─────┘               │
    │          │ review              │ submit (after fix)
    │     ┌────┴────┐                │
    │     ▼         ▼                │
┌──────────┐   ┌──────────┐          │
│ APPROVED │   │ REJECTED │──────────┘
└──────────┘   └──────────┘  (fix + resubmit)
```

- Initial state: `SUBMITTED` (no DRAFT)
- Terminal state: `APPROVED`
- Rejected verifications can cycle back through fix → submit → review indefinitely
- PUT (data edit and/or reassignment) is allowed in `SUBMITTED` and `REJECTED` states

---

## 7. Constraints & Edge Cases

- **One active verification per step**: Cannot create a new verification for a step that already has one in SUBMITTED/REJECTED status. Must complete or delete the existing one first.
- **Step type restriction**: Only DEFECT_REPORT and DEFECT_FOLLOW_UP steps are eligible. Server returns HTTP 400 for other types.
- **Source step must exist and not be deleted**: HTTP 400 if missing/deleted.
- **Self-verify blocked at server level**: Even if a user has VERIFY level, they cannot be assigned as verifier for their own steps. HTTP 403.
- **Only assigned verifier can review**: HTTP 403 if `current_user.id != verification.verifier_id`.
- **Verifier must have VERIFY access level**: Validated at creation and on reassignment via PUT. HTTP 400 if the target inspector lacks VERIFY level.
- **Review staleness check**: POST `/review` requires `server_modified_at` matching the current verification value. If the inspector edited the verification after the verifier read it, the timestamps won't match and the review is rejected with HTTP 409. The verifier must re-read the verification before reviewing.
- **Concurrent modifications**: Standard optimistic locking applies to verification PUT. Copy-back on approval uses the same transaction to avoid partial writes.
- **Original step locked during active verification**: While a verification is in SUBMITTED state, the original inspection step should not be modified via the normal inspection PUT flow. This prevents divergence between the verification copy and the source. Implementation: check for active verification in `InspectionRepository.save()` and reject with HTTP 409 if found.
- **No physical deletion**: Verifications use logical deletion (`is_deleted`). Approved verifications are kept permanently for audit trail.
- **Reassignment resets reviewer context**: When verifier is reassigned via PUT, the new verifier sees the current state of the verification data and all prior events. No data is lost.
- **Data edits while SUBMITTED**: The inspector can modify verification data fields at any time (SUBMITTED or REJECTED). Each edit bumps `server_modified_at`, which invalidates any pending review attempt until the verifier re-reads.
