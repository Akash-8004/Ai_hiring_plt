import React, { useEffect, useState } from "react";
import {
  Users,
  UserPlus,
  Shield,
  CheckCircle,
  XCircle,
  Lock,
  Mail,
  User,
  Power,
  Sparkles,
  Info,
  X,
  Copy,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";
import { CompanyActivityLog } from "./CompanyActivityLog";

export function TeamManagementView() {
  const [teamData, setTeamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  // New sub-user form state
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [permissions, setPermissions] = useState(["conduct_interviews", "view_pipeline"]);
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState("");
  const [createdUser, setCreatedUser] = useState(null);
  const [copied, setCopied] = useState(false);

  const fetchTeam = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetchJson("/api/company/team");
      setTeamData(data);
    } catch (err) {
      setError(err.message || "Failed to load team data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeam();
  }, []);

  const handleToggleStatus = async (userId, currentStatus) => {
    const action = currentStatus === "active" ? "suspend" : "activate";
    if (action === "suspend" && !window.confirm("Suspend this team member's access?")) {
      return;
    }
    try {
      await apiFetchJson(`/api/company/team/${userId}/${action}`, { method: "POST" });
      await fetchTeam();
    } catch (err) {
      alert(err.message || `Failed to ${action} user.`);
    }
  };

  const handlePermissionToggle = (perm) => {
    if (permissions.includes(perm)) {
      setPermissions(permissions.filter((p) => p !== perm));
    } else {
      setPermissions([...permissions, perm]);
    }
  };

  const handleCreateSubUser = async (e) => {
    e.preventDefault();
    setFormError("");
    setFormLoading(true);

    try {
      const data = await apiFetchJson("/api/company/team", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim(),
          password,
          permissions,
        }),
      });

      setCreatedUser({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
      });

      await fetchTeam();
    } catch (err) {
      setFormError(err.message || "Failed to create team member.");
    } finally {
      setFormLoading(false);
    }
  };

  const handleCopyCredentials = () => {
    if (!createdUser) return;
    const text = `Name: ${createdUser.fullName}\nEmail: ${createdUser.email}\nTemporary Password: ${createdUser.password}\nLogin Portal: ${window.location.origin}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleCloseModal = () => {
    setFullName("");
    setEmail("");
    setPassword("");
    setPermissions(["conduct_interviews", "view_pipeline"]);
    setFormError("");
    setCreatedUser(null);
    setModalOpen(false);
  };

  const maxUsers = teamData?.max_users || 5;
  const currentCount = teamData?.current_count || 0;
  const isLimitReached = currentCount >= maxUsers;

  return (
    <div className="team-management-view">
      {/* Plan & Seats Header Banner */}
      <div className="team-banner card">
        <div className="banner-left">
          <div className="badge plan-badge">{teamData?.plan?.toUpperCase()} PLAN</div>
          <h2 className="banner-title">Team Member Access Management</h2>
          <p className="banner-subtitle">
            Manage your internal HR staff and interviewers. You can add up to {maxUsers} user seats under your current subscription tier.
          </p>
        </div>

        <div className="banner-right">
          <div className="seat-stat-box">
            <span className="seat-stat-label">Seats Used</span>
            <span className="seat-stat-value">
              {currentCount} / {maxUsers}
            </span>
            <div className="progress-bar-bg mt-2">
              <div
                className="progress-bar-fill"
                style={{ width: `${Math.min(100, (currentCount / maxUsers) * 100)}%` }}
              />
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setModalOpen(true)}
            disabled={isLimitReached || loading}
          >
            <UserPlus size={16} /> Add Team Member
          </button>
        </div>
      </div>

      {isLimitReached && (
        <div className="notice warning my-4">
          <span>
            You have reached the maximum seat limit ({maxUsers}/{maxUsers}) for your <strong>{teamData?.plan?.toUpperCase()}</strong> plan. Contact the platform Super Admin to upgrade your subscription for more user seats.
          </span>
        </div>
      )}

      {error ? <div className="notice error my-4">{error}</div> : null}

      {/* Team Members Table */}
      <div className="card mt-4">
        <div className="card-header-flex">
          <div className="card-title-group">
            <Users size={18} className="text-primary" />
            <h3 className="card-title">Company Team Members ({teamData?.users?.length || 0})</h3>
          </div>
        </div>

        <div className="table-responsive mt-3">
          <table className="data-table">
            <thead>
              <tr>
                <th>Member Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Permissions</th>
                <th>Status</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-muted">
                    Loading team members...
                  </td>
                </tr>
              ) : teamData?.users?.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-muted">
                    No team members found. Click "Add Team Member" to invite an HR staff member.
                  </td>
                </tr>
              ) : (
                teamData?.users?.map((member) => (
                  <tr key={member._id}>
                    <td>
                      <div className="member-name-cell">
                        <div className="member-avatar">
                          {member.full_name?.slice(0, 2).toUpperCase() || "U"}
                        </div>
                        <span className="font-semibold">{member.full_name}</span>
                      </div>
                    </td>
                    <td className="font-mono text-sm">{member.email}</td>
                    <td>
                      <span
                        className={`badge ${
                          member.role === "company_admin" ? "role-badge-company" : "role-badge-user"
                        }`}
                      >
                        {member.role === "company_admin" ? "Company Admin" : "HR / Interviewer"}
                      </span>
                    </td>
                    <td>
                      <div className="flex-row flex-wrap gap-1">
                        {member.role === "company_admin" ? (
                          <span className="badge badge-subtle">Full Access</span>
                        ) : member.permissions?.length ? (
                          member.permissions.map((p) => (
                            <span key={p} className="badge badge-subtle">
                              {p.replace(/_/g, " ")}
                            </span>
                          ))
                        ) : (
                          <span className="text-muted text-xs">None</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        className={`badge status-badge ${
                          member.status === "active" ? "status-active" : "status-suspended"
                        }`}
                      >
                        {member.status === "active" ? "Active" : "Suspended"}
                      </span>
                    </td>
                    <td className="text-xs text-muted">
                      {member.last_login ? new Date(member.last_login).toLocaleDateString() : "Never"}
                    </td>
                    <td>
                      {member.role !== "company_admin" && (
                        <button
                          className={`btn btn-xs ${member.status === "active" ? "btn-danger" : "btn-primary"}`}
                          onClick={() => handleToggleStatus(member._id, member.status)}
                        >
                          {member.status === "active" ? "Suspend" : "Activate"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Company-scoped activity log for the team */}
      <CompanyActivityLog />

      {/* Add Sub-User Modal */}
      {modalOpen && (
        <div className="modal-overlay">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <div className="modal-title-group">
                <UserPlus size={20} className="text-primary" />
                <h2 className="modal-title">
                  {createdUser ? "User Account Ready" : "Add Internal HR / Interviewer"}
                </h2>
              </div>
              <button className="btn-icon" onClick={handleCloseModal}>
                <X size={18} />
              </button>
            </div>

            {createdUser ? (
              <div className="modal-body success-step">
                <div className="success-banner">
                  <CheckCircle size={32} className="text-success" />
                  <h3>Account Created for {createdUser.fullName}</h3>
                  <p>Credentials have been generated. Share these credentials with your team member so they can log in.</p>
                </div>

                <div className="credentials-box">
                  <div className="credential-row">
                    <span className="label">Login Email:</span>
                    <span className="value">{createdUser.email}</span>
                  </div>
                  <div className="credential-row">
                    <span className="label">Password:</span>
                    <span className="value font-mono">{createdUser.password}</span>
                  </div>
                </div>

                <div className="modal-footer">
                  <button className="btn btn-secondary" onClick={handleCopyCredentials}>
                    {copied ? (
                      <>
                        <CheckCircle size={16} /> Copied to Clipboard
                      </>
                    ) : (
                      <>
                        <Copy size={16} /> Copy Credentials
                      </>
                    )}
                  </button>
                  <button className="btn btn-primary" onClick={handleCloseModal}>
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateSubUser}>
                <div className="modal-body">
                  {formError ? <div className="notice error mb-4">{formError}</div> : null}

                  <div className="form-group">
                    <label className="form-label">Full Name *</label>
                    <input
                      type="text"
                      className="input-field"
                      placeholder="e.g. Sarah Jenkins"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Work Email *</label>
                    <input
                      type="email"
                      className="input-field"
                      placeholder="sarah@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password *</label>
                    <input
                      type="text"
                      className="input-field font-mono"
                      placeholder="Minimum 8 characters (e.g. Employee@123)"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      minLength={8}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Access Permissions</label>
                    <div className="permissions-checkbox-list">
                      <label className="checkbox-item">
                        <input
                          type="checkbox"
                          checked={permissions.includes("conduct_interviews")}
                          onChange={() => handlePermissionToggle("conduct_interviews")}
                        />
                        <span>Conduct & Review AI Voice Interviews</span>
                      </label>
                      <label className="checkbox-item">
                        <input
                          type="checkbox"
                          checked={permissions.includes("view_pipeline")}
                          onChange={() => handlePermissionToggle("view_pipeline")}
                        />
                        <span>View Candidates & Hiring Pipeline</span>
                      </label>
                      <label className="checkbox-item">
                        <input
                          type="checkbox"
                          checked={permissions.includes("manage_resumes")}
                          onChange={() => handlePermissionToggle("manage_resumes")}
                        />
                        <span>Upload & Parse Resumes</span>
                      </label>
                    </div>
                  </div>
                </div>

                <div className="modal-footer">
                  <button type="button" className="btn btn-secondary" onClick={handleCloseModal} disabled={formLoading}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={formLoading}>
                    {formLoading ? "Creating..." : "Create Account"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
