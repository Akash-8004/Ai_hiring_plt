import React, { useEffect, useState } from "react";
import { AlertTriangle, CalendarClock, X } from "lucide-react";

/**
 * Reason codes accepted by the backend. Must stay in sync with
 * OVERRIDE_REASONS in backend/main.py — the server validates against its own
 * copy and rejects anything it does not recognise.
 */
export const OVERRIDE_REASONS = [
  { value: "strong_resume", label: "Strong resume / screening mis-scored" },
  { value: "referral", label: "Referred by a team member" },
  { value: "recruiter_request", label: "Direct request from the hiring manager" },
  { value: "candidate_experience", label: "Relevant experience the rubric missed" },
  { value: "role_priority", label: "Urgent / priority role" },
];

const MAX_NOTE = 500;

function toInputValue(deadline) {
  if (!deadline) return "";
  const date = new Date(deadline);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function defaultFutureDeadline() {
  const d = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  d.setSeconds(0, 0);
  return toInputValue(d.toISOString());
}

/**
 * Confirmation & configuration dialog for:
 * 1. Inviting a candidate past a pipeline gate they did not clear (override reason required)
 * 2. Inviting a candidate after the drive round deadline passed (per-candidate window required)
 * 3. Amending a live invitation's window
 * 4. Or both combined (override + custom deadline)
 */
export function OverrideReasonDialog({
  candidateName,
  round,
  gateLabel,
  onConfirm,
  onClose,
  busy,
  needsOverride = true,
  needsDeadline = false,
  isAmend = false,
  initialDeadline = "",
}) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [deadline, setDeadline] = useState(() => toInputValue(initialDeadline) || defaultFutureDeadline());

  useEffect(() => {
    setReason("");
    setNote("");
    setDeadline(toInputValue(initialDeadline) || defaultFutureDeadline());
  }, [initialDeadline]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, busy]);

  const roundLabel = round === "hr" ? "HR" : "Technical";

  let title = `Override ${roundLabel} round gate`;
  if (isAmend) {
    title = `Amend ${roundLabel} round window`;
  } else if (needsOverride && needsDeadline) {
    title = `Override ${roundLabel} gate & set window`;
  } else if (!needsOverride && needsDeadline) {
    title = `Set custom ${roundLabel} window`;
  }

  const canSubmit =
    (!needsOverride || Boolean(reason)) &&
    (!needsDeadline || Boolean(deadline)) &&
    !busy;

  const handleConfirm = () => {
    let isoDeadline = "";
    if (deadline) {
      const parsed = new Date(deadline);
      if (!Number.isNaN(parsed.getTime())) {
        isoDeadline = parsed.toISOString();
      }
    }
    onConfirm({
      reason: needsOverride ? reason : undefined,
      note: needsOverride ? note : undefined,
      deadline: isoDeadline || undefined,
    });
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 10000 }}>
      <div
        className="modal-content modal-md"
        role="dialog"
        aria-modal="true"
        aria-labelledby="override-dialog-title"
      >
        <div className="modal-header">
          <div className="modal-title-group">
            {isAmend || (!needsOverride && needsDeadline) ? (
              <CalendarClock size={20} style={{ color: "#4f46e5" }} />
            ) : (
              <AlertTriangle size={20} style={{ color: "#d97706" }} />
            )}
            <h2 className="modal-title" id="override-dialog-title">
              {title}
            </h2>
          </div>
          <button className="btn-icon" onClick={onClose} disabled={busy} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <p style={{ margin: "0 0 1rem", lineHeight: 1.55 }}>
            {isAmend ? (
              <>
                Update the interview window for <strong>{candidateName}</strong>. The candidate's invitation link remains valid until the new deadline.
              </>
            ) : needsOverride && needsDeadline ? (
              <>
                <strong>{candidateName}</strong> did not clear {gateLabel}, and the drive-level {roundLabel} deadline has passed. An override reason and custom interview window are required.
              </>
            ) : needsOverride ? (
              <>
                <strong>{candidateName}</strong> did not clear {gateLabel}. You can still invite them to the {roundLabel} round, but this bypass is recorded against your account for audit.
              </>
            ) : (
              <>
                The drive-level {roundLabel} deadline has passed. Set a private per-candidate interview window for <strong>{candidateName}</strong> (up to 14 days) to allow them to take the interview.
              </>
            )}
          </p>

          {needsOverride && (
            <>
              <div className="form-group">
                <label className="form-label" htmlFor="override-reason">
                  Reason <span style={{ color: "#dc2626" }}>*</span>
                </label>
                <select
                  id="override-reason"
                  className="input-field"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  autoFocus
                >
                  <option value="">Select a reason...</option>
                  {OVERRIDE_REASONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="override-note">
                  Note <span className="text-muted">(optional)</span>
                </label>
                <textarea
                  id="override-note"
                  className="input-field"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={MAX_NOTE}
                  rows={3}
                  placeholder="Add context for whoever reviews this later..."
                />
                <div className="text-xs text-muted" style={{ marginTop: 4, textAlign: "right" }}>
                  {note.length}/{MAX_NOTE}
                </div>
              </div>
            </>
          )}

          {needsDeadline && (
            <div className="form-group">
              <label className="form-label" htmlFor="custom-deadline">
                Per-Candidate Window Deadline <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <input
                id="custom-deadline"
                type="datetime-local"
                className="input-field"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                min={toInputValue(new Date().toISOString())}
                autoFocus={!needsOverride}
                required
              />
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                A private window cannot extend more than 14 days into the future.
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleConfirm}
            disabled={!canSubmit}
          >
            {busy
              ? "Saving..."
              : isAmend
              ? "Update Window"
              : needsOverride
              ? `Confirm Override & Invite`
              : `Send Invitation`}
          </button>
        </div>
      </div>
    </div>
  );
}
