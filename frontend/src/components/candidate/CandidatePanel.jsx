import React, { useState } from "react";
import { XCircle, Video, Play, X } from "lucide-react";
import { StatusBadge } from "../common/StatusBadge";
import { CopyButton } from "../common/CopyButton";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function CandidatePanel({ candidate, onClose }) {
  const hrInvitation = candidate.hr_invitation;
  const hrInterview = candidate.hr_interview || {};
  const invitation = candidate.invitation;
  const techInterview = candidate.technical_interview || {};

  const [videoModal, setVideoModal] = useState(null); // { email, type, label }
  const [videoUrl, setVideoUrl] = useState(null);
  const [videoLoading, setVideoLoading] = useState(false);

  async function openRecording(email, type, label) {
    setVideoModal({ email, type, label });
    setVideoUrl(null);
    setVideoLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/interview/recording/${encodeURIComponent(email)}/${type}`);
      if (!res.ok) throw new Error("Recording not found");
      const data = await res.json();
      // Use presigned URL if available, otherwise use local file endpoint
      if (data.url) {
        setVideoUrl(data.url);
      } else if (data.local_path) {
        const filename = data.local_path.split(/[/\\]/).pop();
        setVideoUrl(`${API_BASE}/api/interview/recording/local/${filename}`);
      }
    } catch (err) {
      console.error("Failed to load recording:", err);
      setVideoUrl(null);
    } finally {
      setVideoLoading(false);
    }
  }

  function closeVideoModal() {
    setVideoModal(null);
    setVideoUrl(null);
  }

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

      {/* HR Interview Section (first — HR comes before Technical) */}
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
            {hrInterview.evaluation?.strengths?.length ? (
              <div className="detail-section">
                <strong>Strengths:</strong>
                <span>{hrInterview.evaluation.strengths.join(", ")}</span>
              </div>
            ) : null}
            {hrInterview.evaluation?.areas_for_improvement?.length ? (
              <div className="detail-section">
                <strong>Areas for Improvement:</strong>
                <span>{hrInterview.evaluation.areas_for_improvement.join(", ")}</span>
              </div>
            ) : null}
            {hrInterview.evaluation?.red_flags?.length ? (
              <div className="detail-section">
                <strong>Red Flags:</strong>
                <span>{hrInterview.evaluation.red_flags.join(", ")}</span>
              </div>
            ) : null}
            {hrInterview.evaluation?.recommendation ? (
              <div className="detail-section">
                <strong>Recommendation:</strong>
                <span>{hrInterview.evaluation.recommendation}</span>
              </div>
            ) : null}
          </div>
        ) : null}
        {hrInterview.recording ? (
          <button
            type="button"
            className="watch-recording-btn"
            onClick={() => openRecording(candidate.Email, "hr", "HR Interview")}
          >
            <Play size={15} /> Watch Recording
          </button>
        ) : null}
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
        {techInterview.recording ? (
          <button
            type="button"
            className="watch-recording-btn"
            onClick={() => openRecording(candidate.Email, "technical", "Technical Interview")}
          >
            <Play size={15} /> Watch Recording
          </button>
        ) : null}
      </section>

      {/* Interview Transcript */}
      {candidate.interview_transcript?.length ? (
        <section>
          <h3>Interview Transcript</h3>
          <div className="transcript-box">
            {candidate.interview_transcript.map((turn, index) => (
              <p key={index} className={turn.role === "candidate" ? "transcript-candidate" : ""}>
                <strong>
                  {turn.type === "written"
                    ? "Candidate (written):"
                    : turn.role === "candidate"
                      ? "Candidate:"
                      : "AI Interviewer:"}
                </strong>{" "}
                {turn.content}
                {turn.question ? <span className="transcript-question"> — {turn.question}</span> : null}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      {/* Video Playback Modal */}
      {videoModal && (
        <div className="video-modal-overlay" onClick={closeVideoModal}>
          <div className="video-modal" onClick={(e) => e.stopPropagation()}>
            <div className="video-modal-header">
              <h3><Video size={18} /> {videoModal.label} Recording</h3>
              <button type="button" className="video-modal-close" onClick={closeVideoModal}>
                <X size={20} />
              </button>
            </div>
            <div className="video-modal-body">
              {videoLoading ? (
                <div className="video-modal-loading">Loading recording...</div>
              ) : videoUrl ? (
                <video
                  key={videoUrl}
                  controls
                  autoPlay
                  className="video-modal-player"
                  src={videoUrl}
                >
                  Your browser does not support video playback.
                </video>
              ) : (
                <div className="video-modal-loading">Recording not available.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
