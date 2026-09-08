import React from "react";
import { CheckCircle2, Clock, FileText, Sparkles, XCircle } from "lucide-react";

// Derive where the candidate currently sits in the hiring pipeline. We check
// the most-advanced stage first and fall back to the resume screening result,
// so the badge always reflects the candidate's *latest* position.
function pipelineStatus(candidate) {
  const hr = candidate.hr_interview || {};
  const tech = candidate.technical_interview || {};
  if (tech.status === "completed") {
    return tech.decision === "PASS"
      ? { label: "Hired", cls: "shortlisted" }
      : { label: "Tech Rejected", cls: "rejected" };
  }
  if (candidate.invitation?.link) return { label: "Tech Invited", cls: "invited" };
  if (hr.status === "completed") {
    return hr.decision === "PASS"
      ? { label: "HR Passed", cls: "shortlisted" }
      : { label: "HR Rejected", cls: "rejected" };
  }
  if (candidate.hr_invitation?.link) return { label: "HR Invited", cls: "invited" };
  return candidate.Status === "Shortlisted"
    ? { label: "Resume Shortlisted", cls: "shortlisted" }
    : { label: "Resume Rejected", cls: "rejected" };
}

const STATUS_ICON = { shortlisted: CheckCircle2, rejected: XCircle, invited: Clock };

// Parsers store "Not found" when a number is absent — treat that as no phone.
function hasPhone(phone) {
  return phone && phone !== "Not found" && phone !== "Not detected";
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export function CandidateTable({ candidates, onCandidate, onViewDetails }) {
  if (!candidates.length) {
    return (
      <div className="empty-state">
        <FileText size={24} />
        <strong>No candidates yet</strong>
        <span>Load sample resumes or add your first candidate.</span>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Candidate</th>
            <th>Experience</th>
            <th>Details</th>
            <th>Status</th>
            <th>AI Summary</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const status = pipelineStatus(candidate);
            const StatusIcon = STATUS_ICON[status.cls];
            return (
              <tr key={`${candidate.Email}-${candidate.Name}`}>
                <td>
                  <strong>{candidate.Name}</strong>
                  <span>{candidate.Email}</span>
                  {hasPhone(candidate.Phone) ? <span>{candidate.Phone}</span> : null}
                </td>
                <td>{candidate.Experience}</td>
                <td>
                  <button
                    className="details-button"
                    onClick={() => onViewDetails(candidate)}
                    title="View resume & parsed details"
                  >
                    <FileText size={15} /> View details
                  </button>
                </td>
                <td>
                  <span className={`status-badge ${status.cls}`}>
                    {StatusIcon ? <StatusIcon size={15} /> : null}
                    {status.label}
                  </span>
                </td>
                <td className="summary-cell">
                  <button
                    className="summary-link"
                    onClick={() => onCandidate(candidate)}
                    title="View AI summary & interview transcript"
                  >
                    <Sparkles size={14} />
                    <span>{candidate.Summary ? truncate(candidate.Summary, 70) : "View summary"}</span>
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
