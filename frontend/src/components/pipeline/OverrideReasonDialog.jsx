import React, { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

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

/**
 * Confirmation dialog for inviting a candidate past a pipeline gate they did
 * not clear. A reason is mandatory: the backend rejects the invite without one,
 * and the choice is stored on the candidate and written to the audit log.
 */
export function OverrideReasonDialog({ candidateName, round, gateLabel, onConfirm, onClose, busy }) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    setReason("");
    setNote("");
  }, []);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, busy]);

  const roundLabel = round === "hr" ? "HR" : "Technical";

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
            <AlertTriangle size={20} style={{ color: "#d97706" }} />
            <h2 className="modal-title" id="override-dialog-title">
              Override {roundLabel} round gate
            </h2>
          </div>
          <button className="btn-icon" onClick={onClose} disabled={busy} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <p style={{ margin: "0 0 1rem", lineHeight: 1.55 }}>
            <strong>{candidateName}</strong> did not clear {gateLabel}. You can still invite
            them to the {roundLabel} round, but this bypass is recorded against your
            account for audit.
          </p>

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
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={() => onConfirm({ reason, note })}
            disabled={!reason || busy}
          >
            {busy ? "Inviting..." : `Invite to ${roundLabel} round`}
          </button>
        </div>
      </div>
    </div>
  );
}
