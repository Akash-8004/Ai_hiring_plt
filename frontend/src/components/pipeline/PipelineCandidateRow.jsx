import React, { useState } from "react";
import { CheckCircle2, Loader2, Mail, Send, XCircle } from "lucide-react";
import { CopyButton } from "../common/CopyButton";

export function PipelineCandidateRow({ candidate, onInvite, onSendEmail, canInvite = false, busy, emailSending }) {
  const hrInvitation = candidate.hr_invitation;
  const hrInterview = candidate.hr_interview || {};
  const invitation = candidate.invitation;
  const techInterview = candidate.technical_interview || {};
  const emailSent = candidate.email_sent || {};

  const isHrEmailSending = emailSending?.[candidate.Email + ":hr"];
  const isTechEmailSending = emailSending?.[candidate.Email + ":technical"];
  const hrEmailSent = !!emailSent.hr;
  const techEmailSent = !!emailSent.technical;

  // --- HR Invitation Cell ---
  let hrInviteCell;
  if (hrInterview.status === "completed") {
    hrInviteCell = (
      <span className="status-badge interviewed">
        <CheckCircle2 size={15} />
        Completed
      </span>
    );
  } else if (hrInvitation?.link && hrEmailSent) {
    hrInviteCell = (
      <span className="status-badge shortlisted">
        <CheckCircle2 size={15} />
        Email Sent
      </span>
    );
  } else if (hrInvitation?.link) {
    hrInviteCell = (
      <div className="invite-link-row">
        <span className="invite-link">{hrInvitation.link.replace(/^https?:\/\//, "")}</span>
        <CopyButton text={hrInvitation.link} />
        {canInvite && (
          <button
            className="icon-button"
            onClick={() => onSendEmail(candidate.Email, "hr")}
            disabled={isHrEmailSending}
            title="Send invite via email"
          >
            {isHrEmailSending ? <Loader2 size={16} className="spin" /> : <Mail size={16} />}
          </button>
        )}
      </div>
    );
  } else if (candidate.Status === "Shortlisted") {
    hrInviteCell = canInvite ? (
      <button className="secondary-button" onClick={() => onInvite(candidate.Email, "hr")} disabled={busy}>
        <Send size={15} />
        Invite
      </button>
    ) : (
      <span className="muted-cell">Awaiting invite</span>
    );
  } else {
    hrInviteCell = <span className="muted-cell">Not shortlisted</span>;
  }

  // --- HR Result Cell ---
  let hrResultCell;
  if (hrInterview.status === "completed") {
    const passed = hrInterview.decision === "PASS";
    hrResultCell = (
      <div className="interview-result">
        <span className={`status-badge ${passed ? "shortlisted" : "rejected"}`}>
          {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {hrInterview.decision}
        </span>
        <span>Score {hrInterview.score}%</span>
      </div>
    );
  } else if (hrInvitation?.link) {
    hrResultCell = <span className="muted-cell">Awaiting candidate</span>;
  } else {
    hrResultCell = <span className="muted-cell">-</span>;
  }

  // --- Technical Round Cell (only available after HR passes) ---
  let techCell;
  if (techInterview.status === "completed") {
    const passed = techInterview.decision === "PASS";
    techCell = (
      <div className="interview-result">
        <span className={`status-badge ${passed ? "shortlisted" : "rejected"}`}>
          {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {techInterview.decision}
        </span>
        <span>Score {techInterview.score}%</span>
      </div>
    );
  } else if (invitation?.link && techEmailSent) {
    techCell = (
      <span className="status-badge shortlisted">
        <CheckCircle2 size={15} />
        Email Sent
      </span>
    );
  } else if (invitation?.link) {
    techCell = (
      <div className="invite-link-row">
        <span className="invite-link">{invitation.link.replace(/^https?:\/\//, "")}</span>
        <CopyButton text={invitation.link} />
        {canInvite && (
          <button
            className="icon-button"
            onClick={() => onSendEmail(candidate.Email, "technical")}
            disabled={isTechEmailSending}
            title="Send invite via email"
          >
            {isTechEmailSending ? <Loader2 size={16} className="spin" /> : <Mail size={16} />}
          </button>
        )}
      </div>
    );
  } else if (hrInterview.decision === "PASS") {
    techCell = canInvite ? (
      <button className="secondary-button" onClick={() => onInvite(candidate.Email, "technical")} disabled={busy}>
        <Send size={15} />
        Invite Tech
      </button>
    ) : (
      <span className="muted-cell">Awaiting invite</span>
    );
  } else {
    techCell = <span className="muted-cell">Pending HR pass</span>;
  }

  return (
    <tr>
      <td>
        <strong>{candidate.Name}</strong>
        <span>{candidate.Email}</span>
      </td>
      <td>{candidate.Score}%</td>
      <td>{hrInviteCell}</td>
      <td>{hrResultCell}</td>
      <td>{techCell}</td>
    </tr>
  );
}
