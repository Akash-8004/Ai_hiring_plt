import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";

// Derive where the candidate currently sits in the hiring pipeline. We check
// the most-advanced stage first and fall back to the resume screening result,
// so the badge always reflects the candidate's *latest* position.
export function pipelineStatus(candidate) {
  if (candidate.noText) {
    return { label: "No Text / Scanned", cls: "unparseable" };
  }
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

export const STATUS_ICON = { shortlisted: CheckCircle2, rejected: XCircle, invited: Clock, unparseable: AlertTriangle };