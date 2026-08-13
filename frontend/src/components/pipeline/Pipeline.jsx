import React from "react";
import { Loader2, Send } from "lucide-react";
import { PipelineCandidateRow } from "./PipelineCandidateRow";

export function Pipeline({ candidates, onInvite, busy }) {
  const uploaded = candidates.length;
  const shortlisted = candidates.filter((c) => c.Status === "Shortlisted");
  const invited = candidates.filter((c) => c.invitation?.link);
  const techDone = candidates.filter((c) => c.technical_interview?.status === "completed");
  const techPassed = candidates.filter((c) => c.technical_interview?.decision === "PASS");
  const hrDone = candidates.filter((c) => c.hr_interview?.status === "completed");
  const hiredList = candidates.filter((c) => c.hr_interview?.decision === "PASS");
  const invitedEmails = new Set(invited.map((c) => c.Email));

  const pipelineStages = [
    ["Uploaded", uploaded],
    ["AI Shortlisted", shortlisted.length],
    ["Tech Invited", invited.length],
    ["Tech Interview", techDone.length],
    ["Tech Passed", techPassed.length],
    ["HR Interview", hrDone.length],
    ["Hired", hiredList.length],
  ];

  return (
    <div className="content-stack">
      <section className="pipeline-strip">
        {pipelineStages.map(([label, value]) => (
          <div className="pipeline-step" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      {/* Technical Interview Section */}
      <section className="table-section">
        <div className="section-toolbar">
          <div>
            <h2>Technical Interview</h2>
            <span>Invite shortlisted candidates to AI technical interview</span>
          </div>
          <button
            className="primary-button"
            onClick={() => {
              shortlisted
                .filter((c) => !invitedEmails.has(c.Email))
                .forEach((c) => onInvite(c.Email, "technical"));
            }}
            disabled={busy || !shortlisted.filter((c) => !invitedEmails.has(c.Email)).length}
          >
            {busy ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
            Invite for Technical
          </button>
        </div>
        {!candidates.length ? (
          <div className="empty-state">
            <Send size={24} />
            <strong>No candidates yet</strong>
            <span>Add resumes first, then invite shortlisted candidates to interviews.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Resume Score</th>
                  <th>Technical Invitation</th>
                  <th>Technical Result</th>
                  <th>HR Round</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => (
                  <PipelineCandidateRow
                    key={`${candidate.Email}-${candidate.Name}`}
                    candidate={candidate}
                    onInvite={onInvite}
                    busy={busy}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
