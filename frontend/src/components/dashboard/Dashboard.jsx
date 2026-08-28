import React from "react";
import {
  BriefcaseBusiness,
  CheckCircle2,
  CircleGauge,
  FileText,
  Monitor,
  Search,
  Upload,
  UserRoundCheck,
  UsersRound,
  XCircle,
} from "lucide-react";
import { Metric } from "../common/Metric";
import { CandidateTable } from "./CandidateTable";
import { DriveSelector } from "../job/DriveSelector";

// Candidate pipeline filters shown in the dashboard dropdown. Kept next to the
// predicate below so the labels and the matching logic never drift apart.
export const CANDIDATE_FILTERS = [
  "All",
  "Resume Shortlisted",
  "Resume Rejected",
  "HR Shortlisted",
  "HR Rejected",
  "Tech Shortlisted",
  "Tech Rejected",
  "All Passed",
];

// True when a candidate belongs in the given pipeline filter. "Shortlisted" here
// means "cleared that round"; "All Passed" means the candidate cleared every round.
export function matchesCandidateFilter(candidate, filter) {
  const hrPass = candidate.hr_interview?.decision === "PASS";
  const hrFail = candidate.hr_interview?.decision === "FAIL";
  const techPass = candidate.technical_interview?.decision === "PASS";
  const techFail = candidate.technical_interview?.decision === "FAIL";
  switch (filter) {
    case "Resume Shortlisted": return candidate.Status === "Shortlisted";
    case "Resume Rejected": return candidate.Status === "Rejected";
    case "HR Shortlisted": return hrPass;
    case "HR Rejected": return hrFail;
    case "Tech Shortlisted": return techPass;
    case "Tech Rejected": return techFail;
    case "All Passed": return candidate.Status === "Shortlisted" && hrPass && techPass;
    default: return true; // "All"
  }
}

export function Dashboard({
  workspace,
  candidates,
  statusFilter,
  query,
  onStatusFilter,
  onQuery,
  onCandidate,
  onGoToJob,
  onGoToUpload,
  drives,
  activeJobId,
  onSwitchDrive,
  onEditDrive,
  onDeleteDrive,
  onCreateDrive,
  canCreateDrive,
  canDeleteDrive,
  maxJobs,
}) {
  const metrics = workspace?.metrics || {};
  const job = workspace?.job || { title: "No drive selected", department: "", location: "", experience_years: 0, required_skills: [] };

  return (
    <section className="content-stack">
      <div className="metrics-grid">
        <Metric icon={FileText} label="Uploaded" value={metrics.uploaded} />
        <Metric icon={UserRoundCheck} label="Shortlisted" value={metrics.shortlisted} tone="green" />
        <Metric icon={XCircle} label="Rejected" value={metrics.rejected} tone="red" />
        <Metric icon={CircleGauge} label="Avg Score" value={`${metrics.averageScore}%`} tone="amber" />
        <Metric icon={UsersRound} label="HR Interviewed" value={metrics.hrInterviewed || 0} tone="blue" />
        <Metric icon={Monitor} label="Tech Interviewed" value={metrics.techInterviewed || 0} tone="purple" />
        <Metric icon={CheckCircle2} label="Hired" value={metrics.hired || 0} tone="green" />
      </div>

      <section className="hero-band">
        <div className="hero-copy">
          <DriveSelector
            drives={drives}
            activeJobId={activeJobId}
            onSwitchDrive={onSwitchDrive}
            onEditDrive={onEditDrive}
            onDeleteDrive={onDeleteDrive}
            onCreateDrive={onCreateDrive}
            canCreateDrive={canCreateDrive}
            canDeleteDrive={canDeleteDrive}
            maxJobs={maxJobs}
            compact
          />
          <span className="pill">Active Job</span>
          <h2>{job.title}</h2>
          <p>{job.department} · {job.location} · {job.experience_years}+ years</p>
          <p className="provider-line">
            Screening: {workspace.screening?.provider || "local"} · {workspace.screening?.model || "template scorer"}
          </p>
          {workspace.screening?.message ? (
            <p className="provider-warning">{workspace.screening.message}</p>
          ) : null}
          <div className="skill-row">
            {job.required_skills.map((skill) => <span key={skill}>{skill}</span>)}
          </div>
        </div>
        <div className="hero-actions">
          {onGoToJob ? (
            <button className="secondary-button" onClick={onGoToJob}>
              <BriefcaseBusiness size={17} />
              Edit JD
            </button>
          ) : null}
          {onGoToUpload ? (
            <button className="primary-button" onClick={onGoToUpload}>
              <Upload size={17} />
              Add Resumes
            </button>
          ) : null}
        </div>
      </section>

      <section className="table-section">
        <div className="section-toolbar">
          <div>
            <h2>Candidate Shortlist</h2>
            <span>{candidates.length} visible candidates</span>
          </div>
          <div className="filters">
            <div className="search-box">
              <Search size={17} />
              <input value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search candidates" />
            </div>
            <select
              className="select-field"
              value={statusFilter}
              onChange={(event) => onStatusFilter(event.target.value)}
              aria-label="Filter candidates by pipeline stage"
            >
              {CANDIDATE_FILTERS.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </div>
        </div>
        <CandidateTable candidates={candidates} onCandidate={onCandidate} />
      </section>
    </section>
  );
}
