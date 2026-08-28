import React from "react";
import { BriefcaseBusiness, Pencil, Plus, Trash2 } from "lucide-react";

export function DriveSelector({
  drives = [],
  activeJobId,
  onSwitchDrive,
  onEditDrive,
  onDeleteDrive,
  onCreateDrive,
  canCreateDrive,
  canDeleteDrive,
  maxJobs = 3,
  compact = false,
}) {
  const atLimit = drives.length >= maxJobs;
  const activeDrive = drives.find((d) => d.job_id === activeJobId);

  if (!drives.length) {
    return (
      <div className={`drive-selector empty ${compact ? "compact" : ""}`}>
        <p className="text-muted text-sm">No drives yet — create your first job drive.</p>
        {canCreateDrive && (
          <button type="button" className="btn btn-primary btn-sm mt-2" onClick={onCreateDrive}>
            <Plus size={14} /> New Drive
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={`drive-selector ${compact ? "compact" : ""}`}>
      <div className="drive-selector-head">
        <BriefcaseBusiness size={16} className="text-primary" />
        <div>
          <strong>{activeDrive?.title || "Select a drive"}</strong>
          {activeJobId && <span className="badge badge-subtle ml-2">Active</span>}
        </div>
        <span className="drive-usage-label text-xs text-muted">
          {drives.length} / {maxJobs} drives
        </span>
      </div>
      <ul className="drive-list">
        {drives.map((drive) => (
          <li key={drive.job_id} className={drive.job_id === activeJobId ? "active" : ""}>
            <div className="drive-list-info">
              <span className="drive-title">{drive.title}</span>
              <span className="text-xs text-muted">
                {drive.department} · {drive.candidate_count ?? 0} candidates
              </span>
            </div>
            <div className="drive-list-actions">
              {drive.job_id !== activeJobId && (
                <button type="button" className="btn btn-secondary btn-xs" onClick={() => onSwitchDrive(drive.job_id)}>
                  Switch
                </button>
              )}
              {canCreateDrive && (
                <button type="button" className="btn btn-secondary btn-xs" onClick={() => onEditDrive(drive.job_id)} title="Edit drive">
                  <Pencil size={12} />
                </button>
              )}
              {canDeleteDrive && (
                <button
                  type="button"
                  className="btn btn-danger btn-xs"
                  onClick={() => onDeleteDrive(drive)}
                  title="Delete drive"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {canCreateDrive && (
        <button
          type="button"
          className="btn btn-primary btn-sm mt-2"
          onClick={onCreateDrive}
          disabled={atLimit}
          title={atLimit ? "Drive limit reached" : "Create a new job drive"}
        >
          <Plus size={14} /> New Drive
        </button>
      )}
    </div>
  );
}
