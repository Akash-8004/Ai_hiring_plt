import React from "react";
import { AlertTriangle, ShieldAlert } from "lucide-react";

export default function ProctoringWarningModal({ activeWarning, onResume }) {
  if (!activeWarning) return null;
  return (
    <div className="proctoring-overlay" role="alertdialog" aria-modal="true">
      <div className="proctoring-modal">
        <div className="proctoring-modal-icon">
          <ShieldAlert size={40} />
        </div>
        <h2>
          <AlertTriangle size={18} /> Proctoring Warning (Strike 1 of 2)
        </h2>
        <p className="proctoring-modal-message">{activeWarning.message}</p>
        <p className="proctoring-modal-note">
          Note: A 2nd violation will automatically submit your assessment immediately.
        </p>
        <button type="button" className="proctoring-resume-btn" onClick={onResume}>
          Re-enter Fullscreen &amp; Resume Test
        </button>
      </div>
    </div>
  );
}
