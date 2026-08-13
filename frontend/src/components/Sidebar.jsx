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
} from "lucide-react";

export function Sidebar({ activeView, onViewChange, company }) {
  const navItems = [
    ["dashboard", LayoutDashboard, "Dashboard"],
    ["job", BriefcaseBusiness, "Job Setup"],
    ["resumes", Upload, "Resume Intake"],
    ["pipeline", BarChart3, "Pipeline"],
    ["settings", Settings, "Settings"],
  ];

  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><Sparkles size={19} /></div>
        <div>
          <strong>HireOS AI</strong>
          <span>SaaS Console</span>
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

      <div className="tenant-card">
        <Building2 size={18} />
        <div>
          <strong>{company?.name || "Company"}</strong>
          <span>{company?.plan || "Growth"} plan</span>
        </div>
      </div>

      <button className="nav-item muted" title="Logout">
        <LogOut size={18} />
        <span>Logout</span>
      </button>
    </aside>
  );
}
