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
  XCircle,
} from "lucide-react";
import { Metric } from "./common/Metric";
import { CandidateTable } from "./CandidateTable";

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
}) {
  const metrics = workspace.metrics;
  const job = workspace.job;

  return (
    <section className="content-stack">
      <div className="metrics-grid">
        <Metric icon={FileText} label="Uploaded" value={metrics.uploaded} />
        <Metric icon={UserRoundCheck} label="Shortlisted" value={metrics.shortlisted} tone="green" />
        <Metric icon={XCircle} label="Rejected" value={metrics.rejected} tone="red" />
        <Metric icon={CircleGauge} label="Avg Score" value={`${metrics.averageScore}%`} tone="amber" />
        <Metric icon={Monitor} label="Tech Interview" value={metrics.techInterviewed || 0} tone="purple" />
        <Metric icon={CheckCircle2} label="Hired" value={metrics.hired || 0} tone="green" />
      </div>

      <section className="hero-band">
        <div className="hero-copy">
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
          <button className="secondary-button" onClick={onGoToJob}>
            <BriefcaseBusiness size={17} />
            Edit JD
          </button>
          <button className="primary-button" onClick={onGoToUpload}>
            <Upload size={17} />
            Add Resumes
          </button>
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
            <div className="segmented">
              {["All", "Shortlisted", "Rejected"].map((status) => (
                <button
                  key={status}
                  className={statusFilter === status ? "active" : ""}
                  onClick={() => onStatusFilter(status)}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>
        </div>
        <CandidateTable candidates={candidates} onCandidate={onCandidate} />
      </section>
    </section>
  );
}
