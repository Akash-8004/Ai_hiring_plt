import React from "react";
import { Loader2, Send, UsersRound } from "lucide-react";
import { PipelineCandidateRow } from "./PipelineCandidateRow";

export function Pipeline({ candidates, onInvite, canInvite = false, busy }) {
  const uploaded = candidates.length;
  const shortlisted = candidates.filter((c) => c.Status === "Shortlisted");
  const hrInvited = candidates.filter((c) => c.hr_invitation?.link);
  const hrDone = candidates.filter((c) => c.hr_interview?.status === "completed");
  const hrPassed = candidates.filter((c) => c.hr_interview?.decision === "PASS");
  const techInvited = candidates.filter((c) => c.invitation?.link);
  const techDone = candidates.filter((c) => c.technical_interview?.status === "completed");
  const techPassed = candidates.filter((c) => c.technical_interview?.decision === "PASS");
  const hiredList = candidates.filter((c) => c.technical_interview?.decision === "PASS" && c.hr_interview?.decision === "PASS");
  const hrInvitedEmails = new Set(hrInvited.map((c) => c.Email));
  const techInvitedEmails = new Set(techInvited.map((c) => c.Email));

  const pipelineStages = [
    ["Uploaded", uploaded],
    ["AI Shortlisted", shortlisted.length],
    ["HR Invited", hrInvited.length],
    ["HR Interview", hrDone.length],
    ["HR Passed", hrPassed.length],
    ["Tech Invited", techInvited.length],
    ["Tech Interview", techDone.length],
    ["Tech Passed", techPassed.length],
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

      {/* HR Interview Section */}
      <section className="table-section">
        <div className="section-toolbar">
          <div>
            <h2><UsersRound size={18} /> HR Interview</h2>
            <span>Invite shortlisted candidates to AI HR interview first</span>
          </div>
          {canInvite ? (
            <button
              className="primary-button"
              onClick={() => {
                shortlisted
                  .filter((c) => !hrInvitedEmails.has(c.Email))
                  .forEach((c) => onInvite(c.Email, "hr"));
              }}
              disabled={busy || !shortlisted.filter((c) => !hrInvitedEmails.has(c.Email)).length}
            >
              {busy ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
              Invite for HR
            </button>
          ) : null}
        </div>
        {!candidates.length ? (
          <div className="empty-state">
            <Send size={24} />
            <strong>No candidates yet</strong>
            <span>Add resumes first, then invite shortlisted candidates to HR interviews.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Resume Score</th>
                  <th>HR Invitation</th>
                  <th>HR Result</th>
                  <th>Technical Round</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => (
                  <PipelineCandidateRow
                    key={`${candidate.Email}-${candidate.Name}`}
                    candidate={candidate}
                    onInvite={onInvite}
                    canInvite={canInvite}
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
