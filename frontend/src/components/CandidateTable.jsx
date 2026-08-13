import React from "react";
import { ChevronRight, FileText } from "lucide-react";
import { StatusBadge } from "./common/StatusBadge";

export function CandidateTable({ candidates, onCandidate }) {
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
            <th>Skills</th>
            <th>Score</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={`${candidate.Email}-${candidate.Name}`}>
              <td>
                <strong>{candidate.Name}</strong>
                <span>{candidate.Email}</span>
              </td>
              <td>{candidate.Experience}</td>
              <td className="skills-cell">{candidate.Skills || "Not detected"}</td>
              <td>
                <div className="score-cell">
                  <div className="score-track"><span style={{ width: `${candidate.Score}%` }} /></div>
                  <strong>{candidate.Score}%</strong>
                </div>
              </td>
              <td><StatusBadge status={candidate.Status} /></td>
              <td>
                <button className="row-action" onClick={() => onCandidate(candidate)} title="View candidate">
                  <ChevronRight size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
