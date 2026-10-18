import React, { useEffect, useState } from "react";
import { CalendarClock, Loader2, Send } from "lucide-react";
import { PipelineCandidateRow } from "./PipelineCandidateRow";

/**
 * Format a stored ISO instant as a `datetime-local` input value.
 *
 * A `datetime-local` value is a *naive* wall-clock string, and the browser
 * parses it back with `new Date(value)` as **local** time (per the ES spec).
 * So the input must be populated with local wall-clock components.
 *
 * Using `toISOString()` here would display UTC, which the save handler would
 * then re-read as local time — shifting the deadline by the browser's UTC
 * offset on every save. In timezones ahead of UTC that walks the deadline
 * backwards until it lands in the past.
 */
function toInputValue(deadline) {
  if (!deadline) return "";
  const date = new Date(deadline);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** The local wall-clock a deadline is displayed at, for confirmation text. */
function formatLocal(deadline) {
  if (!deadline) return "";
  const date = new Date(deadline);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, { timeZone: "Asia/Kolkata" });
}

/**
 * The viewer's UTC offset, so a deadline set by one teammate is unambiguous to
 * the next. Without this, a UTC-stored deadline looks shifted by hours.
 */
function localTimeZoneLabel() {
  return "IST";
}

function deadlineStatus(deadline) {
  if (!deadline) return "No deadline set";
  const remaining = new Date(deadline).getTime() - Date.now();
  if (remaining <= 0) return "Expired";
  const hours = Math.ceil(remaining / 3600000);
  return `${Math.floor(hours / 24)}d ${hours % 24}h remaining`;
}

export function Pipeline({ candidates, onInvite, onReopen, onRefresh, onDeadline, deadlines = {}, canInvite = false, busy }) {
  const [deadlineValues, setDeadlineValues] = useState({ hr: toInputValue(deadlines.hr), technical: toInputValue(deadlines.technical) });

  useEffect(() => {
    setDeadlineValues({ hr: toInputValue(deadlines.hr), technical: toInputValue(deadlines.technical) });
  }, [deadlines.hr, deadlines.technical]);

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
  const techLocked = !deadlines.hr_passed && !!deadlines.hr;
  const technicalRoundActive = !!deadlines.hr_passed;
  const activeRoundHasDeadline = technicalRoundActive
    ? !!deadlines.technical && !deadlines.technical_passed
    : !!deadlines.hr && !deadlines.hr_passed;

  function deadlineControl(type, label) {
    const deadline = deadlines[type];
    return (
      <div className="deadline-control">
        <label>{label}</label>
        <div>
          <input type="datetime-local" value={deadlineValues[type]} onChange={(event) => setDeadlineValues((prev) => ({ ...prev, [type]: event.target.value }))} disabled={!canInvite || busy} />
          <button className="secondary-button" onClick={() => onDeadline(type, deadlineValues[type] ? new Date(deadlineValues[type]).toISOString() : null)} disabled={!canInvite || busy}>
            <CalendarClock size={15} /> Set / Update
          </button>
          {deadline ? <button className="text-button" onClick={() => onDeadline(type, null)} disabled={!canInvite || busy}>Clear</button> : null}
        </div>
        <span className={deadline && new Date(deadline) <= new Date() ? "deadline-expired" : "muted-cell"}>
          {deadlineStatus(deadline)}
          {deadline ? ` · ${formatLocal(deadline)} (${localTimeZoneLabel()})` : ""}
        </span>
      </div>
    );
  }

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
    ["Overrides", candidates.filter((c) => c.overrides?.length).length],
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

      <section className="table-section">
        <div className="section-toolbar">
          <div>
            {technicalRoundActive
              ? deadlineControl("technical", "Technical deadline")
              : deadlineControl("hr", "HR deadline")}
          </div>
          {canInvite ? (
            <button
              className="primary-button"
              onClick={async () => {
                const invitees = (technicalRoundActive ? hrPassed : shortlisted)
                  .filter((c) => !c.late_entry)
                  .filter((c) => !(technicalRoundActive ? techInvitedEmails : hrInvitedEmails).has(c.Email));
                await Promise.all(invitees.map((c) => onInvite(c.Email, technicalRoundActive ? "technical" : "hr")));
                if (onRefresh) await onRefresh();
              }}
              disabled={
                busy ||
                !activeRoundHasDeadline ||
                !(technicalRoundActive ? hrPassed : shortlisted)
                  .filter((c) => !c.late_entry)
                  .filter((c) => !(technicalRoundActive ? techInvitedEmails : hrInvitedEmails).has(c.Email)).length
              }
            >
              {busy ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
              {technicalRoundActive ? "Invite for Technical" : "Invite for HR"}
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
                    onReopen={onReopen}
                    canInvite={canInvite}
                    busy={busy}
                    techLocked={techLocked}
                    hrDeadlineSet={!!deadlines.hr && !deadlines.hr_passed}
                    technicalDeadlineSet={!!deadlines.technical && !deadlines.technical_passed}
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
