import React from "react";
import { CheckCircle2, Send, XCircle } from "lucide-react";
import { CopyButton } from "./common/CopyButton";

export function PipelineCandidateRow({ candidate, onInvite, busy }) {
  const invitation = candidate.invitation;
  const techInterview = candidate.technical_interview || {};
  const hrInvitation = candidate.hr_invitation;
  const hrInterview = candidate.hr_interview || {};

  // --- Technical Invitation Cell ---
  let techInviteCell;
  if (techInterview.status === "completed") {
    techInviteCell = (
      <span className="status-badge interviewed">
        <CheckCircle2 size={15} />
        Completed
      </span>
    );
  } else if (invitation?.link) {
    techInviteCell = (
      <div className="invite-link-row">
        <span className="invite-link">{invitation.link.replace(/^https?:\/\//, "")}</span>
        <CopyButton text={invitation.link} />
      </div>
    );
  } else if (candidate.Status === "Shortlisted") {
    techInviteCell = (
      <button className="secondary-button" onClick={() => onInvite(candidate.Email, "technical")} disabled={busy}>
        <Send size={15} />
        Invite
      </button>
    );
  } else {
    techInviteCell = <span className="muted-cell">Not shortlisted</span>;
  }

  // --- Technical Result Cell ---
  let techResultCell;
  if (techInterview.status === "completed") {
    const passed = techInterview.decision === "PASS";
    techResultCell = (
      <div className="interview-result">
        <span className={`status-badge ${passed ? "shortlisted" : "rejected"}`}>
          {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {techInterview.decision}
        </span>
        <span>Score {techInterview.score}%</span>
      </div>
    );
  } else if (invitation?.link) {
    techResultCell = <span className="muted-cell">Awaiting candidate</span>;
  } else {
    techResultCell = <span className="muted-cell">—</span>;
  }

  // --- HR Round Cell ---
  let hrCell;
  if (hrInterview.status === "completed") {
    const passed = hrInterview.decision === "PASS";
    hrCell = (
      <div className="interview-result">
        <span className={`status-badge ${passed ? "shortlisted" : "rejected"}`}>
          {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {hrInterview.decision}
        </span>
        <span>Score {hrInterview.score}%</span>
      </div>
    );
  } else if (hrInvitation?.link) {
    hrCell = (
      <div className="invite-link-row">
        <span className="invite-link">{hrInvitation.link.replace(/^https?:\/\//, "")}</span>
        <CopyButton text={hrInvitation.link} />
      </div>
    );
  } else if (techInterview.decision === "PASS") {
    hrCell = (
      <button className="secondary-button" onClick={() => onInvite(candidate.Email, "hr")} disabled={busy}>
        <Send size={15} />
        Invite HR
      </button>
    );
  } else {
    hrCell = <span className="muted-cell">—</span>;
  }

  return (
    <tr>
      <td>
        <strong>{candidate.Name}</strong>
        <span>{candidate.Email}</span>
      </td>
      <td>{candidate.Score}%</td>
      <td>{techInviteCell}</td>
      <td>{techResultCell}</td>
      <td>{hrCell}</td>
    </tr>
  );
}
