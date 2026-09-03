import React, { useState } from "react";
import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  ChevronDown,
  Gauge,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  Upload,
  Users,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

export function Sidebar({
  activeView,
  onViewChange,
  company,
  drives = [],
  activeJobId,
}) {
  const { user, role, logout, hasPermission } = useAuth();
  const [planOpen, setPlanOpen] = useState(false);

  const planName = (company?.plan || "starter").toUpperCase();
  const seatsUsed = company?.current_users;
  const maxUsers = company?.max_users;
  const maxCandidates = company?.max_candidates;
  const credits = company?.credits;
  const creditsUsed = credits?.used;
  const creditsAllowance = credits?.allowance;
  const creditsRemaining = credits?.remaining;
  const activeDrive = drives.find((d) => d.job_id === activeJobId);

  const isCompanyAdmin = role === "company_admin" || role === "super_admin";
  const canManageJobs = isCompanyAdmin || hasPermission("manage_jobs");

  const navItems = [
    ["dashboard", LayoutDashboard, "Dashboard"],
    ...(canManageJobs ? [["job", BriefcaseBusiness, "Job Drives"]] : []),
    ...(hasPermission("manage_resumes") ? [["resumes", Upload, "Resume Intake"]] : []),
    ...(hasPermission("view_pipeline") ? [["pipeline", BarChart3, "Pipeline"]] : []),
    ...(isCompanyAdmin || hasPermission("view_usage") ? [["usage", Gauge, "Usage"]] : []),
    ...(isCompanyAdmin ? [["team", Users, "Team Access"]] : []),
    ["settings", Settings, "Settings"],
  ];

  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><Sparkles size={19} /></div>
        <div>
          <strong>AI Hiring SaaS</strong>
          <span>Enterprise Portal</span>
        </div>
      </div>

      <nav className="nav-list">
        {navItems.map(([key, Icon, label]) => (
          <button
            key={key}
            className={activeView === key ? "nav-item active" : "nav-item"}
            onClick={() => onViewChange(key)}
            title={label}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer-group">
        <div className="tenant-card-wrap">
          <button
            type="button"
            className={`tenant-card tenant-card-button ${planOpen ? "active" : ""}`}
            onClick={() => setPlanOpen((open) => !open)}
            title="View subscription plan details"
          >
            <Building2 size={18} className="text-primary" />
            <div className="tenant-info-text">
              <strong className="truncate">{user?.company_name || company?.name || "Company"}</strong>
              <span>{planName} PLAN</span>
            </div>
            <ChevronDown size={15} className={`tenant-chevron ${planOpen ? "open" : ""}`} />
          </button>

          {planOpen && (
            <div className="plan-popover">
              <div className="plan-popover-head">
                <span className="plan-popover-tier">{planName}</span>
                <span className="plan-popover-label">Current Plan</span>
              </div>
              <ul className="plan-popover-list">
                <li>
                  <span>User seats</span>
                  <strong>{seatsUsed != null ? `${seatsUsed} / ${maxUsers ?? "—"}` : `${maxUsers ?? "—"}`}</strong>
                </li>
                <li>
                  <span>Candidate limit</span>
                  <strong>Up to {maxCandidates ? maxCandidates.toLocaleString() : "—"}</strong>
                </li>
                <li>
                  <span>Job drives</span>
                  <strong>{drives.length} (unlimited)</strong>
                </li>
                {activeDrive ? (
                  <li>
                    <span>Current drive</span>
                    <strong className="truncate">{activeDrive.title}</strong>
                  </li>
                ) : null}
                <li>
                  <span>Credits</span>
                  <strong>
                    {creditsUsed != null && creditsAllowance != null
                      ? `${creditsUsed} / ${creditsAllowance}`
                      : "—"}
                    {creditsRemaining != null ? ` (${creditsRemaining} left)` : ""}
                  </strong>
                </li>
              </ul>
              <p className="plan-popover-foot">Contact your platform admin to change your plan.</p>
            </div>
          )}
        </div>

        <div className="user-profile-badge-card">
          <div className="user-profile-avatar">
            {user?.full_name?.slice(0, 2).toUpperCase() || "US"}
          </div>
          <div className="user-profile-meta">
            <span className="user-profile-name truncate">{user?.full_name || "User"}</span>
            <span className="user-profile-role">
              {role === "company_admin" ? "Company Admin" : role === "super_admin" ? "Super Admin" : "HR Staff"}
            </span>
          </div>
          <button
            className="btn-icon btn-logout-sidebar"
            onClick={logout}
            title="Sign Out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
