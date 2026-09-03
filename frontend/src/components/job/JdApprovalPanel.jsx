import React, { useState } from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  Eye,
  ArrowRight,
  FileText,
  Sparkles,
  X,
  AlertCircle,
  Check,
  Building2,
  ListFilter,
  Trash2,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";

function fieldsSummary(proposed) {
  if (!proposed) return "";
  const skills = Array.isArray(proposed.required_skills)
    ? proposed.required_skills.join(", ")
    : proposed.required_skills;
  return [
    `Dept: ${proposed.department || "-"}`,
    `Loc: ${proposed.location || "-"}`,
    `${proposed.experience_years ?? 0}+ yrs exp`,
    `Threshold: ${proposed.threshold ?? 80}%`,
  ]
    .concat(skills ? [`Skills: ${skills}`] : [])
    .join(" · ");
}

function normalizeVal(val) {
  if (val === undefined || val === null) return "";
  if (Array.isArray(val)) return val.map((s) => String(s).trim()).filter(Boolean).join(", ");
  return String(val).trim();
}

function isFieldModified(currentVal, proposedVal) {
  return normalizeVal(currentVal) !== normalizeVal(proposedVal);
}

export function JdApprovalPanel({ requests = [], onResolved, isCompanyAdmin = true }) {
  const [busyId, setBusyId] = useState(null);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [rejectNote, setRejectNote] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);

  const pending = requests.filter((r) => r.status === "pending");

  async function handleAction(requestId, action, note = "") {
    setBusyId(requestId);
    try {
      const opts = { method: "POST" };
      if (action === "reject" && note) {
        opts.body = JSON.stringify({ note });
      }
      await apiFetchJson(`/api/job/requests/${requestId}/${action}`, opts);
      setSelectedRequest(null);
      setShowRejectInput(false);
      setRejectNote("");
      if (onResolved) onResolved();
    } catch (err) {
      alert(`Could not ${action} request: ${err.message}`);
    } finally {
      setBusyId(null);
    }
  }

  // ── Employee View: tracking their own submitted proposals ─────────────────
  if (!isCompanyAdmin) {
    if (!requests.length) return null;
    return (
      <section className="form-panel wide approve-panel">
        <div className="approve-panel-head">
          <h2>
            <FileText size={18} className="text-primary" />
            My Submitted Drive Proposals
          </h2>
          <span className="pill">{requests.length} proposal{requests.length === 1 ? "" : "s"}</span>
        </div>
        <div className="approve-list">
          {requests.map((req) => {
            const proposed = req.proposed || {};
            const isCreate = req.target_status === "create";
            const isDelete = req.target_status === "delete";
            const isPending = req.status === "pending";
            const isApproved = req.status === "approved";
            return (
              <div
                className="approve-item"
                key={req._id || req.job_id}
                style={{
                  borderLeftColor: isPending ? "#f59e0b" : isApproved ? "#10b981" : "#ef4444",
                }}
              >
                <div className="approve-item-main">
                  <div className="flex-row gap-2 align-center">
                    <strong>
                      {isDelete
                        ? "Drive Deletion Proposal"
                        : isCreate
                        ? "New Drive Proposal"
                        : "Drive Edit Proposal"}
                      : {proposed.title || "(untitled)"}
                    </strong>
                    <span
                      className={`badge status-badge ${
                        isPending
                          ? "shortlisted"
                          : isApproved
                          ? "status-active"
                          : "status-suspended"
                      }`}
                    >
                      {isPending ? (
                        <>
                          <Clock size={12} /> Pending Admin Review
                        </>
                      ) : isApproved ? (
                        <>
                          <Check size={12} /> Approved
                        </>
                      ) : (
                        <>
                          <X size={12} /> Rejected
                        </>
                      )}
                    </span>
                  </div>
                  <span className="text-xs text-muted">
                    Submitted on {req.requested_at ? new Date(req.requested_at).toLocaleString() : "Recently"}
                    {req.reviewed_at && ` · Reviewed on ${new Date(req.reviewed_at).toLocaleDateString()}`}
                  </span>
                  {isDelete ? (
                    <p className="text-sm text-danger">
                      Deletion requested for drive with {proposed.candidate_count ?? 0} candidate(s).
                    </p>
                  ) : (
                    <p className="text-sm text-muted">{fieldsSummary(proposed)}</p>
                  )}
                  {req.review_note && (
                    <div className="text-xs text-danger mt-1">
                      <strong>Admin note:</strong> {req.review_note}
                    </div>
                  )}
                </div>
                <div className="approve-item-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => setSelectedRequest(req)}
                  >
                    <Eye size={12} /> View Details
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Read-only detail modal for employee */}
        {selectedRequest && (
          <ReviewDetailModal
            request={selectedRequest}
            onClose={() => setSelectedRequest(null)}
            isCompanyAdmin={false}
          />
        )}
      </section>
    );
  }

  // ── Company Admin View: no pending requests ──────────────────────────────
  if (!pending.length) {
    return (
      <section className="form-panel wide approve-panel">
        <div className="approve-panel-head">
          <h2>
            <CheckCircle2 size={18} className="text-success" />
            Job Drive Change Approvals
          </h2>
          <span className="pill">All caught up</span>
        </div>
        <p className="panel-hint">
          When team members submit requests to create or update job drives, they will appear here for your verification and approval.
        </p>
      </section>
    );
  }

  // ── Company Admin View: pending approval requests ─────────────────────────
  return (
    <section className="form-panel wide approve-panel">
      <div className="approve-panel-head">
        <h2>
          <Clock size={18} className="text-warning" />
          Job Drive Change Approvals
        </h2>
        <span className="badge status-badge shortlisted">
          <Clock size={14} /> {pending.length} pending approval
        </span>
      </div>

      <div className="approve-list">
        {pending.map((req) => {
          const proposed = req.proposed || {};
          const isCreate = req.target_status === "create";
          const isDelete = req.target_status === "delete";
          return (
            <div
              className="approve-item"
              key={req._id || req.job_id}
              style={{ borderLeftColor: isDelete ? "#ef4444" : "#f59e0b" }}
            >
              <div className="approve-item-main">
                <div className="flex-row gap-2 align-center">
                  <span
                    className={`badge ${
                      isDelete
                        ? "status-badge status-suspended"
                        : isCreate
                        ? "role-badge-company"
                        : "role-badge-user"
                    }`}
                  >
                    {isDelete ? "Drive Deletion Request" : isCreate ? "New Drive Request" : "Drive Edit Request"}
                  </span>
                  <strong style={{ fontSize: "1rem" }}>
                    {isDelete ? `Delete "${proposed.title}"` : proposed.title || "(Untitled Drive)"}
                  </strong>
                </div>
                <span className="text-xs text-muted mt-1">
                  Requested by <strong>{req.requested_by_name || req.requested_by_email || "Team Member"}</strong>
                  {req.requested_by_email && ` (${req.requested_by_email})`} ·{" "}
                  {req.requested_at ? new Date(req.requested_at).toLocaleString() : ""}
                </span>
                {isDelete ? (
                  <p className="text-sm text-danger mt-1">
                    ⚠️ Request to permanently delete this drive and all {proposed.candidate_count ?? 0} candidate(s).
                  </p>
                ) : (
                  <p className="text-sm mt-1">{fieldsSummary(proposed)}</p>
                )}
              </div>

              <div className="approve-item-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setSelectedRequest(req);
                    setShowRejectInput(false);
                    setRejectNote("");
                  }}
                  title={isDelete ? "Inspect drive deletion details" : "Inspect all proposed changes and verify side-by-side"}
                >
                  <Eye size={14} /> {isDelete ? "Review Request" : "Review & Verify"}
                </button>
                <button
                  type="button"
                  className={isDelete ? "btn btn-danger btn-sm" : "primary-button small"}
                  style={isDelete ? {} : { background: "#10b981", borderColor: "#10b981" }}
                  onClick={() => handleAction(req._id, "approve")}
                  disabled={busyId === req._id}
                  title={isDelete ? "Approve and permanently delete this drive" : "Approve and apply this job drive directly"}
                >
                  {busyId === req._id ? <Loader2 size={14} className="spin" /> : isDelete ? <Trash2 size={14} /> : <CheckCircle2 size={14} />}
                  {isDelete ? "Approve Deletion" : "Approve"}
                </button>
                <button
                  type="button"
                  className="secondary-button small danger"
                  onClick={() => {
                    setSelectedRequest(req);
                    setShowRejectInput(true);
                  }}
                  disabled={busyId === req._id}
                  title="Reject this proposal with an optional note"
                >
                  <XCircle size={14} /> Reject
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Verification & Diff Modal */}
      {selectedRequest && (
        <ReviewDetailModal
          request={selectedRequest}
          onClose={() => {
            setSelectedRequest(null);
            setShowRejectInput(false);
            setRejectNote("");
          }}
          onApprove={() => handleAction(selectedRequest._id, "approve")}
          onReject={(note) => handleAction(selectedRequest._id, "reject", note)}
          busy={busyId === selectedRequest._id}
          isCompanyAdmin={true}
          initialShowReject={showRejectInput}
        />
      )}
    </section>
  );
}

// ── Detailed Review & Verification Modal ──────────────────────────────────────
function ReviewDetailModal({
  request,
  onClose,
  onApprove,
  onReject,
  busy,
  isCompanyAdmin = true,
  initialShowReject = false,
}) {
  const [rejectNote, setRejectNote] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(initialShowReject);

  const proposed = request.proposed || {};
  const current = request.current || {};
  const isCreate = request.target_status === "create";
  const isDelete = request.target_status === "delete";

  const fieldsToCompare = [
    { label: "Job Title", key: "title" },
    { label: "Department", key: "department" },
    { label: "Location", key: "location" },
    { label: "Min Experience (Years)", key: "experience_years", format: (v) => `${v ?? 0} yrs` },
    { label: "Shortlist Threshold", key: "threshold", format: (v) => `${v ?? 80}%` },
    { label: "HR Round Duration", key: "hr_interview_duration", format: (v) => `${v ?? 7} mins` },
    { label: "Technical Round Duration", key: "technical_interview_duration", format: (v) => `${v ?? 5} mins` },
    { label: "Required Skills", key: "required_skills", isArray: true },
    { label: "Nice to Have Skills", key: "nice_to_have_skills", isArray: true },
    { label: "Education", key: "education" },
    { label: "Job Description / Responsibilities", key: "description", isLong: true },
  ];

  return (
    <div className="modal-overlay" style={{ zIndex: 9999 }}>
      <div className="modal-content modal-lg" style={{ maxWidth: 880, maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            {isDelete ? <Trash2 size={20} className="text-danger" /> : <Sparkles size={20} className="text-primary" />}
            <div>
              <h2 className="modal-title">
                {isDelete
                  ? "Verify Drive Deletion Request"
                  : isCreate
                  ? "Verify New Job Drive Proposal"
                  : "Verify Proposed Changes to Drive"}
              </h2>
              <span className="text-xs text-muted">
                Requested by <strong>{request.requested_by_name || request.requested_by_email || "Team Member"}</strong>
                {request.requested_by_email && ` (${request.requested_by_email})`} ·{" "}
                {request.requested_at ? new Date(request.requested_at).toLocaleString() : ""}
              </span>
            </div>
          </div>
          <button className="btn-icon" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="modal-body" style={{ overflowY: "auto", padding: "1.25rem" }}>
          {isDelete ? (
            /* Drive Deletion Warning & Confirmation */
            <div className="form-grid" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div className="card" style={{ padding: "1.25rem", border: "1px solid #ef4444", background: "#fef2f2" }}>
                <div className="flex-row gap-2 align-center mb-2">
                  <AlertCircle size={22} className="text-danger" />
                  <h3 style={{ margin: 0, color: "#991b1b", fontSize: "1.05rem" }}>
                    Permanent Drive Deletion Request
                  </h3>
                </div>
                <p style={{ color: "#7f1d1d", fontSize: "0.92rem", margin: "0 0 1rem 0", lineHeight: 1.5 }}>
                  A team member has requested to permanently delete the job drive <strong>"{proposed.title}"</strong>.
                  Approving this request will permanently remove the drive and delete all <strong>{proposed.candidate_count ?? 0} candidate profiles, resumes, evaluations, and transcripts</strong>.
                </p>
                <div className="usage-stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", background: "#fff", padding: "0.85rem 1rem", borderRadius: "8px", border: "1px solid #fecaca" }}>
                  <div>
                    <span className="usage-stat-label">Drive Title</span>
                    <strong>{proposed.title || "—"}</strong>
                  </div>
                  <div>
                    <span className="usage-stat-label">Department</span>
                    <strong>{proposed.department || "—"}</strong>
                  </div>
                  <div>
                    <span className="usage-stat-label">Candidates to be Deleted</span>
                    <strong className="text-danger">{proposed.candidate_count ?? 0}</strong>
                  </div>
                </div>
              </div>
            </div>
          ) : isCreate ? (
            /* New Drive Overview */
            <div className="form-grid" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div className="notice info">
                <strong>New Drive Proposal:</strong> This drive will be added to your active drives once approved.
              </div>

              <div className="usage-stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
                <div>
                  <span className="usage-stat-label">Title</span>
                  <strong>{proposed.title || "—"}</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Department</span>
                  <strong>{proposed.department || "—"}</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Location</span>
                  <strong>{proposed.location || "—"}</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Min Experience</span>
                  <strong>{proposed.experience_years ?? 0} yrs</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Shortlist Threshold</span>
                  <strong>{proposed.threshold ?? 80}%</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Durations</span>
                  <strong>HR: {proposed.hr_interview_duration ?? 7}m · Tech: {proposed.technical_interview_duration ?? 5}m</strong>
                </div>
              </div>

              <div className="card" style={{ padding: "1rem", background: "#f9fafb" }}>
                <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem" }}>Job Description</h4>
                <p style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: "0.9rem", color: "#374151" }}>
                  {proposed.description || "(No description provided)"}
                </p>
              </div>

              <div className="card" style={{ padding: "1rem", background: "#f9fafb" }}>
                <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem" }}>Skills & Requirements</h4>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <span className="text-xs text-muted font-semibold">Required Skills:</span>
                    <p style={{ margin: "4px 0 0 0", fontSize: "0.9rem" }}>
                      {normalizeVal(proposed.required_skills) || "None"}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-muted font-semibold">Nice to Have:</span>
                    <p style={{ margin: "4px 0 0 0", fontSize: "0.9rem" }}>
                      {normalizeVal(proposed.nice_to_have_skills) || "None"}
                    </p>
                  </div>
                </div>
                <div style={{ marginTop: "0.75rem" }}>
                  <span className="text-xs text-muted font-semibold">Education:</span>
                  <p style={{ margin: "4px 0 0 0", fontSize: "0.9rem" }}>{proposed.education || "Any"}</p>
                </div>
              </div>

              {proposed.custom_questions && proposed.custom_questions.length > 0 && (
                <div className="card" style={{ padding: "1rem", background: "#f9fafb" }}>
                  <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem" }}>
                    Custom Technical Questions ({proposed.custom_questions.length})
                  </h4>
                  <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.9rem" }}>
                    {proposed.custom_questions.map((q, i) => (
                      <li key={i} style={{ marginBottom: "4px" }}>
                        {q.question} <span className="text-xs text-muted">({q.topic || "General"} · {q.difficulty || "medium"})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            /* Drive Edit: Field-by-Field Comparison */
            <div>
              <div className="notice info mb-3">
                <strong>Changes Comparison:</strong> Review the current drive values against what the team member has proposed. Modified fields are highlighted.
              </div>

              <div className="table-responsive">
                <table className="data-table" style={{ width: "100%", fontSize: "0.9rem" }}>
                  <thead>
                    <tr>
                      <th style={{ width: "25%" }}>Field</th>
                      <th style={{ width: "35%" }}>Current Active Drive</th>
                      <th style={{ width: "40%" }}>Proposed Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fieldsToCompare.map(({ label, key, format, isArray, isLong }) => {
                      const curVal = current[key];
                      const propVal = proposed[key];
                      const modified = isFieldModified(curVal, propVal);

                      const curDisplay = format ? format(curVal) : normalizeVal(curVal);
                      const propDisplay = format ? format(propVal) : normalizeVal(propVal);

                      return (
                        <tr
                          key={key}
                          style={{
                            backgroundColor: modified ? "rgba(245, 158, 11, 0.08)" : "transparent",
                          }}
                        >
                          <td className="font-semibold" style={{ verticalAlign: "top" }}>
                            {label}
                            {modified && (
                              <span
                                className="badge status-badge shortlisted"
                                style={{ display: "block", width: "fit-content", marginTop: "4px", fontSize: "0.7rem" }}
                              >
                                Modified
                              </span>
                            )}
                          </td>
                          <td style={{ verticalAlign: "top", color: modified ? "#6b7280" : "inherit" }}>
                            <div style={{ whiteSpace: isLong ? "pre-wrap" : "normal", maxHeight: isLong ? 150 : "none", overflowY: isLong ? "auto" : "visible" }}>
                              {curDisplay || <span className="text-muted">—</span>}
                            </div>
                          </td>
                          <td style={{ verticalAlign: "top", color: modified ? "#059669" : "inherit", fontWeight: modified ? 600 : "normal" }}>
                            <div style={{ whiteSpace: isLong ? "pre-wrap" : "normal", maxHeight: isLong ? 150 : "none", overflowY: isLong ? "auto" : "visible" }}>
                              {propDisplay || <span className="text-muted">—</span>}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Rejection Note Section */}
          {isCompanyAdmin && showRejectForm && (
            <div className="card mt-4" style={{ padding: "1rem", border: "1px solid #ef4444", background: "#fef2f2" }}>
              <div className="flex-row gap-2 align-center mb-2">
                <AlertCircle size={16} className="text-danger" />
                <strong className="text-danger">Reason for Rejection (Optional)</strong>
              </div>
              <textarea
                className="input-field full"
                rows={3}
                placeholder="Explain to the team member why this proposal cannot be accepted..."
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
              />
              <div className="flex-row gap-2 mt-2 justify-end">
                <button
                  type="button"
                  className="btn btn-secondary btn-xs"
                  onClick={() => setShowRejectForm(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-xs"
                  disabled={busy}
                  onClick={() => onReject(rejectNote)}
                >
                  Confirm Rejection
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {isCompanyAdmin && (
          <div className="modal-footer" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1rem 1.25rem", borderTop: "1px solid #e5e7eb" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onClose}
              disabled={busy}
            >
              Close
            </button>

            <div className="flex-row gap-2">
              {!showRejectForm && (
                <button
                  type="button"
                  className="secondary-button small danger"
                  disabled={busy}
                  onClick={() => setShowRejectForm(true)}
                >
                  <XCircle size={15} /> Reject Proposal
                </button>
              )}
              <button
                type="button"
                className="primary-button small"
                style={{
                  background: isDelete ? "#ef4444" : "#10b981",
                  borderColor: isDelete ? "#ef4444" : "#10b981",
                }}
                disabled={busy}
                onClick={onApprove}
              >
                {busy ? (
                  <Loader2 size={15} className="spin" />
                ) : isDelete ? (
                  <Trash2 size={15} />
                ) : (
                  <CheckCircle2 size={15} />
                )}
                {isDelete
                  ? "Approve & Delete Drive"
                  : isCreate
                  ? "Approve & Create Drive"
                  : "Approve & Apply Changes"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
