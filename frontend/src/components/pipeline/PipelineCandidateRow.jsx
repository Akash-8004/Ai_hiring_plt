import React, { useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, Clock, RotateCcw, Send, ShieldAlert, XCircle } from "lucide-react";
import { CopyButton } from "../common/CopyButton";
import { OverrideReasonDialog } from "./OverrideReasonDialog";

function expiryLabel(invitation, onAmend, canInvite, busy) {
  if (!invitation?.expires_at) return null;
  const date = new Date(invitation.expires_at);
  const isExpired = date <= new Date();
  const isCustom = invitation.deadline_source === "per_candidate";
  return (
    <div className="invite-expiry-wrap" style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      <small className={isExpired ? "deadline-expired" : "invite-expiry"}>
        Expires: {date.toLocaleString()}
        {isCustom ? " (Private window)" : ""}
      </small>
      {!isExpired && canInvite && onAmend ? (
        <button
          type="button"
          className="btn-amend-window"
          onClick={onAmend}
          disabled={busy}
          title="Amend candidate interview window"
        >
          Amend
        </button>
      ) : null}
    </div>
  );
}

/** Badges for any pipeline gates this candidate was waved past by an admin. */
function OverrideBadges({ overrides }) {
  if (!overrides?.length) return null;
  return (
    <div className="invite-link-stack">
      {overrides.map((entry, index) => (
        <span
          key={`${entry.round}-${index}`}
          className="status-badge invited"
          title={`${entry.reason_label || entry.reason}${entry.note ? ` — ${entry.note}` : ""} · by ${entry.by_email || "unknown"}`}
        >
          <ShieldAlert size={13} />
          {entry.round === "hr" ? "HR override" : "Tech override"}
        </span>
      ))}
    </div>
  );
}

export function PipelineCandidateRow({
  candidate,
  onInvite,
  onReopen,
  canInvite = false,
  busy,
  techLocked = false,
  hrDeadlineSet = false,
  technicalDeadlineSet = false,
}) {
  const [overridePrompt, setOverridePrompt] = useState(null);
  const hrInvitation = candidate.hr_invitation;
  const hrInterview = candidate.hr_interview || {};
  const invitation = candidate.invitation;
  const techInterview = candidate.technical_interview || {};
  const emailSent = candidate.email_sent || {};
  const overrides = candidate.overrides || [];

  const hrEmailSent = !!emailSent.hr;
  const techEmailSent = !!emailSent.technical;

  // A round is an override when the candidate did not clear the gate that
  // normally guards it. The backend requires a reason for exactly these.
  const hrNeedsOverride = candidate.Status !== "Shortlisted";
  const techNeedsOverride = hrInterview.decision === "FAIL";

  const inviteDirect = (type) => onInvite(candidate.Email, type);
  const confirmPrompt = async ({ reason, note, deadline }) => {
    const type = overridePrompt.type;
    setOverridePrompt(null);
    await onInvite(candidate.Email, type, { reason, note, deadline });
  };

  const openAmend = (type) => {
    const inv = type === "hr" ? hrInvitation : invitation;
    setOverridePrompt({
      type,
      needsOverride: false,
      needsDeadline: true,
      isAmend: true,
      initialDeadline: inv?.expires_at || "",
    });
  };

  const inviteButton = (type, label) => {
    const needsOverride = type === "hr" ? hrNeedsOverride : techNeedsOverride;
    const deadlineSet = type === "hr" ? hrDeadlineSet : technicalDeadlineSet;
    const isLate = type === "hr" && Boolean(candidate.late_entry);
    const needsDeadline = !deadlineSet || isLate;

    if (!canInvite) return <span className="muted-cell">Awaiting invite</span>;
    return (
      <button
        className="secondary-button"
        onClick={() => {
          if (needsOverride || needsDeadline) {
            setOverridePrompt({
              type,
              needsOverride,
              needsDeadline,
              initialDeadline:
                (type === "hr" ? hrInvitation : invitation)?.expires_at ||
                candidate.per_candidate_expires_at?.[type] ||
                "",
            });
          } else {
            inviteDirect(type);
          }
        }}
        disabled={busy}
        title={
          needsOverride && needsDeadline
            ? "Candidate did not clear gate & drive deadline passed — override reason and custom window required"
            : needsOverride
            ? "This candidate did not clear the gate — a reason will be required"
            : needsDeadline
            ? "Drive deadline passed — custom interview window required"
            : undefined
        }
      >
        <Send size={15} />
        {label}
      </button>
    );
  };

  const reopenButton = (type) => (
    <button
      type="button"
      className="secondary-button small"
      onClick={() => onReopen(candidate.Email, type)}
      disabled={busy}
      title="Re-open this interview for a fresh attempt"
    >
      <RotateCcw size={14} />
      Reopen
    </button>
  );

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
      <div className="invite-link-stack">
        <div className="invite-link-row">
          <span className="invite-link">{hrInvitation.link.replace(/^https?:\/\//, "")}</span>
          <CopyButton text={hrInvitation.link} />
        </div>
        <span className="status-badge shortlisted"><CheckCircle2 size={15} />Email Sent</span>
        {expiryLabel(hrInvitation, () => openAmend("hr"), canInvite, busy)}
      </div>
    );
  } else if (hrInvitation?.link) {
    hrInviteCell = (
      <div className="invite-link-stack">
        <div className="invite-link-row">
          <span className="invite-link">{hrInvitation.link.replace(/^https?:\/\//, "")}</span>
          <CopyButton text={hrInvitation.link} />
        </div>
        {expiryLabel(hrInvitation, () => openAmend("hr"), canInvite, busy)}
      </div>
    );
  } else if (candidate.Status === "Shortlisted") {
    hrInviteCell = inviteButton("hr", "Invite");
  } else {
    hrInviteCell = inviteButton("hr", "Still Invite");
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
  } else if (hrInterview.status === "in_progress") {
    hrResultCell = (
      <div className="interview-result">
        <span className="status-badge invited">
          <Clock size={15} />
          {hrInterview.abandoned_at ? "Left early" : "In progress"}
        </span>
        {canInvite && onReopen ? reopenButton("hr") : null}
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
  } else if (techInterview.status === "in_progress") {
    techCell = (
      <div className="interview-result">
        <span className="status-badge invited">
          <Clock size={15} />
          {techInterview.abandoned_at ? "Left early" : "In progress"}
        </span>
        {canInvite && onReopen ? reopenButton("technical") : null}
      </div>
    );
  } else if (invitation?.link && techEmailSent) {
    techCell = (
      <div className="invite-link-stack">
        <div className="invite-link-row">
          <span className="invite-link">{invitation.link.replace(/^https?:\/\//, "")}</span>
          <CopyButton text={invitation.link} />
        </div>
        <span className="status-badge shortlisted"><CheckCircle2 size={15} />Email Sent</span>
        {expiryLabel(invitation, () => openAmend("technical"), canInvite, busy)}
      </div>
    );
  } else if (invitation?.link) {
    techCell = (
      <div className="invite-link-stack">
        <div className="invite-link-row">
          <span className="invite-link">{invitation.link.replace(/^https?:\/\//, "")}</span>
          <CopyButton text={invitation.link} />
        </div>
        {expiryLabel(invitation, () => openAmend("technical"), canInvite, busy)}
      </div>
    );
  } else if (techLocked) {
    techCell = <span className="muted-cell">Unlocks after HR deadline</span>;
  } else if (hrInterview.decision === "PASS") {
    techCell = inviteButton("technical", "Invite Tech");
  } else if (hrInterview.decision === "FAIL") {
    techCell = inviteButton("technical", "Still Invite");
  } else {
    techCell = <span className="muted-cell">Pending HR pass</span>;
  }

  return (
    <>
      <tr>
        <td>
          <strong>{candidate.Name}</strong>
          <span>{candidate.Email}</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
            {candidate.late_entry ? (
              <span
                className="status-badge late-entry"
                title="Uploaded after drive HR deadline passed. Requires a per-candidate window to invite."
              >
                <Clock size={13} />
                Late Entry
              </span>
            ) : null}
            <OverrideBadges overrides={overrides} />
          </div>
        </td>
        <td>{candidate.Score}%</td>
        <td>{hrInviteCell}</td>
        <td>{hrResultCell}</td>
        <td>{techCell}</td>
      </tr>

      {/* Portalled to <body>: a fixed-position overlay is invalid inside <tr>/<tbody>. */}
      {overridePrompt
        ? createPortal(
            <OverrideReasonDialog
              candidateName={candidate.Name || candidate.Email}
              round={overridePrompt.type}
              gateLabel={overridePrompt.type === "hr" ? "resume screening" : "the HR round"}
              onConfirm={confirmPrompt}
              onClose={() => setOverridePrompt(null)}
              busy={busy}
              needsOverride={overridePrompt.needsOverride}
              needsDeadline={overridePrompt.needsDeadline}
              isAmend={overridePrompt.isAmend}
              initialDeadline={overridePrompt.initialDeadline}
            />,
            document.body
          )
        : null}
    </>
  );
}
