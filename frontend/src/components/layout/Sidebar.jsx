import React from "react";
import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  Upload,
  Users,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

export function Sidebar({ activeView, onViewChange, company }) {
  const { user, role, logout } = useAuth();

  const isCompanyAdmin = role === "company_admin" || role === "super_admin";

  const navItems = [
    ["dashboard", LayoutDashboard, "Dashboard"],
    ...(isCompanyAdmin ? [["job", BriefcaseBusiness, "Job Setup"]] : []),
    ["resumes", Upload, "Resume Intake"],
    ["pipeline", BarChart3, "Pipeline"],
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
        <div className="tenant-card">
          <Building2 size={18} className="text-primary" />
          <div className="tenant-info-text">
            <strong className="truncate">{user?.company_name || company?.name || "Company"}</strong>
            <span>{company?.plan?.toUpperCase() || "STARTER"} PLAN</span>
          </div>
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
