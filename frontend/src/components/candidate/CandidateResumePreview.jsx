import React from "react";
import { XCircle } from "lucide-react";

function value(value, fallback = "Not available") {
  return value && value !== "Not found" ? value : fallback;
}

function linkHref(url) {
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

export function CandidateResumePreview({ candidate, onClose }) {
  return (
    <aside className="candidate-preview">
      <button className="icon-button panel-close" onClick={onClose} title="Close">
        <XCircle size={18} />
      </button>
      <div className="candidate-head">
        <div className="avatar">{candidate.Name?.slice(0, 1) || "?"}</div>
        <div>
          <h2>{candidate.Name}</h2>
          <span>{candidate.Email}</span>
        </div>
      </div>

      <section>
        <h3>Extracted Candidate Details</h3>
        <dl className="candidate-detail-grid">
          <div><dt>Location</dt><dd>{value(candidate.location)}</dd></div>
          <div><dt>Experience</dt><dd>{candidate.Experience || "Not available"}</dd></div>
          <div><dt>Education</dt><dd>{value(candidate.education)}</dd></div>
          <div><dt>Phone</dt><dd>{value(candidate.Phone)}</dd></div>
        </dl>
      </section>

      <section>
        <h3>Skills, Tools & Technologies</h3>
        <div className="skill-row compact">
          {candidate.extractedSkills?.length
            ? candidate.extractedSkills.map((skill) => <span key={skill}>{skill}</span>)
            : candidate.Skills
              ? candidate.Skills.split(", ").map((skill) => <span key={skill}>{skill}</span>)
              : <span>Not available</span>}
        </div>
      </section>

      <section>
        <h3>Professional Links</h3>
        <div className="candidate-link-cards">
          <div className="candidate-link-card">
            <strong>LinkedIn</strong>
            {candidate.linkedin ? (
              <a href={linkHref(candidate.linkedin)} target="_blank" rel="noreferrer">{candidate.linkedin}</a>
            ) : (
              <span className="muted-cell">Not available</span>
            )}
          </div>
          <div className="candidate-link-card">
            <strong>Other links</strong>
            {candidate.otherLinks?.length ? candidate.otherLinks.map((link) => (
              <a key={`${link.label}-${link.url}`} href={linkHref(link.url)} target="_blank" rel="noreferrer">
                {link.label}: {link.url}
              </a>
            )) : <span className="muted-cell">No other links found</span>}
          </div>
        </div>
      </section>

      {candidate.professionalSummary ? (
        <section>
          <h3>Professional Summary</h3>
          <p>{candidate.professionalSummary}</p>
        </section>
      ) : null}

      <section>
        <h3>Uploaded Resume</h3>
        {candidate.resumeText ? (
          <div className="resume-text-box">
            {candidate.resumeText.split(/\r?\n/).map((line, index) => (
              line.trim() ? <div key={index}>{line}</div> : <div key={index} className="resume-text-break" />
            ))}
          </div>
        ) : (
          <p className="muted-cell">No stored resume text is available for this candidate.</p>
        )}
      </section>
    </aside>
  );
}
