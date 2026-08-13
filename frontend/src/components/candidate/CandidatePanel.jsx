import React from "react";
import { XCircle } from "lucide-react";
import { StatusBadge } from "../common/StatusBadge";
import { CopyButton } from "../common/CopyButton";

export function CandidatePanel({ candidate, onClose }) {
  const invitation = candidate.invitation;
  const techInterview = candidate.technical_interview || {};
  const hrInvitation = candidate.hr_invitation;
  const hrInterview = candidate.hr_interview || {};

  return (
    <aside className="candidate-panel">
      <button className="icon-button panel-close" onClick={onClose} title="Close"><XCircle size={18} /></button>
      <div className="candidate-head">
        <div className="avatar">{candidate.Name.slice(0, 1)}</div>
        <div>
          <h2>{candidate.Name}</h2>
          <span>{candidate.Email}</span>
        </div>
      </div>
      <StatusBadge status={candidate.Status} />
      <div className="panel-score">
        <strong>{candidate.Score}%</strong>
        <span>AI resume score</span>
      </div>
      <section>
        <h3>AI Summary</h3>
        <p>{candidate.Summary}</p>
      </section>
      <section>
        <h3>Matched Skills</h3>
        <div className="skill-row compact">
          {(candidate.Matched || "None").split(", ").map((skill) => <span key={skill}>{skill}</span>)}
        </div>
      </section>
      <section>
        <h3>Score Breakdown</h3>
        <div className="breakdown-list">
          {Object.entries(candidate.breakdown || {}).map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <div><i style={{ width: `${value}%` }} /></div>
              <strong>{value}%</strong>
            </div>
          ))}
        </div>
      </section>

      {/* Technical Interview Section */}
      <section>
        <h3>Technical Interview</h3>
        {invitation?.link ? (
          <div className="invite-link-row">
            <span className="invite-link">{invitation.link.replace(/^https?:\/\//, "")}</span>
            <CopyButton text={invitation.link} />
          </div>
        ) : (
          <p className="muted-cell">No technical interview invitation yet.</p>
        )}
        {techInterview.status === "completed" ? (
          <div className="interview-summary">
            <div>
              <strong>{techInterview.decision}</strong>
              <span>Technical Score {techInterview.score}%</span>
            </div>
            {techInterview.evaluation?.feedback ? <p>{techInterview.evaluation.feedback}</p> : null}
            {techInterview.evaluation?.technical_strengths?.length ? (
              <div className="detail-section">
                <strong>Strengths:</strong>
                <span>{techInterview.evaluation.technical_strengths.join(", ")}</span>
              </div>
            ) : null}
            {techInterview.evaluation?.technical_gaps?.length ? (
              <div className="detail-section">
                <strong>Gaps:</strong>
                <span>{techInterview.evaluation.technical_gaps.join(", ")}</span>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* HR Interview Section */}
      <section>
        <h3>HR Interview</h3>
        {hrInvitation?.link ? (
          <div className="invite-link-row">
            <span className="invite-link">{hrInvitation.link.replace(/^https?:\/\//, "")}</span>
            <CopyButton text={hrInvitation.link} />
          </div>
        ) : (
          <p className="muted-cell">No HR interview invitation yet.</p>
        )}
        {hrInterview.status === "completed" ? (
          <div className="interview-summary">
            <div>
              <strong>{hrInterview.decision}</strong>
              <span>HR Score {hrInterview.score}%</span>
            </div>
            {hrInterview.evaluation?.feedback ? <p>{hrInterview.evaluation.feedback}</p> : null}
          </div>
        ) : null}
      </section>

      {/* Interview Transcript */}
      {candidate.interview_transcript?.length ? (
        <section>
          <h3>Interview Transcript</h3>
          <div className="transcript-box">
            {candidate.interview_transcript.map((turn, index) => (
              <p key={index} className={turn.role === "candidate" ? "transcript-candidate" : ""}>
                <strong>{turn.role === "candidate" ? "Candidate:" : "AI Interviewer:"}</strong>{" "}
                {turn.content}
              </p>
            ))}
          </div>
        </section>
      ) : null}
    </aside>
  );
}
