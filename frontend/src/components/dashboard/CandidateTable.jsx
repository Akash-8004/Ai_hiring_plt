import React from "react";
import { AlertTriangle, FileText, Sparkles } from "lucide-react";
import { pipelineStatus, STATUS_ICON } from "../../utils/pipelineStatus";

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
                  <div className="candidate-name-wrap">
                    <strong>{candidate.Name}</strong>
                    {candidate.noText ? (
                      <span
                        className="no-text-tag"
                        title="No readable text extracted. Document may be a scanned image or empty/corrupt file."
                      >
                        <AlertTriangle size={12} /> No text extracted
                      </span>
                    ) : candidate.parsingProvider === "gemini-ocr" || (typeof candidate.parsingProvider === "string" && candidate.parsingProvider.endsWith("-ocr")) ? (
                      <span
                        className="ocr-badge"
                        title="Transcribed from scanned/image document via Gemini Vision OCR"
                      >
                        <Sparkles size={11} /> OCR Transcribed
                      </span>
                    ) : null}
                  </div>
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
