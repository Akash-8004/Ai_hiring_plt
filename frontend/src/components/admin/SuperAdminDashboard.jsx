import React, { useEffect, useState } from "react";
import {
  Building2,
  Users,
  FileText,
  Activity,
  Plus,
  ShieldCheck,
  Power,
  RefreshCw,
  Search,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Briefcase,
  Layers,
  Sparkles,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";
import { useAuth } from "../../hooks/useAuth";
import { CompanyOnboardingModal } from "./CompanyOnboardingModal";
import { ActivityLogViewer } from "./ActivityLogViewer";

export function SuperAdminDashboard() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState("overview"); // 'overview' | 'companies' | 'users' | 'logs'
  const [stats, setStats] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [selectedCompanyForLogs, setSelectedCompanyForLogs] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const refreshAllData = async () => {
    setLoading(true);
    setError("");
    try {
      const [statsData, companiesData, usersData] = await Promise.all([
        apiFetchJson("/api/admin/stats"),
        apiFetchJson("/api/admin/companies"),
        apiFetchJson("/api/admin/users"),
      ]);
      setStats(statsData);
      setCompanies(companiesData.companies || []);
      setUsers(usersData.users || []);
    } catch (err) {
      setError(err.message || "Failed to load platform dashboard data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshAllData();
  }, []);

  const handleToggleCompanyStatus = async (companyId, currentStatus) => {
    const action = currentStatus === "active" ? "suspend" : "activate";
    if (action === "suspend" && !window.confirm("Are you sure you want to suspend this company? All their users will lose access.")) {
      return;
    }
    try {
      await apiFetchJson(`/api/admin/companies/${companyId}/${action}`, { method: "POST" });
      await refreshAllData();
    } catch (err) {
      alert(err.message || `Failed to ${action} company.`);
    }
  };

  const handleToggleUserStatus = async (userId, currentStatus) => {
    const action = currentStatus === "active" ? "suspend" : "activate";
    if (action === "suspend" && !window.confirm("Are you sure you want to suspend this user?")) {
      return;
    }
    try {
      await apiFetchJson(`/api/admin/users/${userId}/${action}`, { method: "POST" });
      await refreshAllData();
    } catch (err) {
      alert(err.message || `Failed to ${action} user.`);
    }
  };

  const handleViewCompanyLogs = (companyId) => {
    setSelectedCompanyForLogs(companyId);
    setActiveTab("logs");
  };

  const filteredCompanies = companies.filter((c) => {
    const q = searchQuery.toLowerCase();
    return c.name.toLowerCase().includes(q) || c.contact_email.toLowerCase().includes(q) || (c.industry || "").toLowerCase().includes(q);
  });

  const filteredUsers = users.filter((u) => {
    const q = searchQuery.toLowerCase();
    return u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q) || u.role.toLowerCase().includes(q);
  });

  return (
    <div className="super-admin-layout">
      {/* Top Navbar */}
      <header className="super-admin-header">
        <div className="header-brand">
          <div className="brand-badge">
            <Sparkles size={20} className="icon-pulse text-primary" />
          </div>
          <div>
            <h1 className="brand-title">AI Hiring Platform</h1>
            <span className="badge role-badge-super">Super Admin Control Center</span>
          </div>
        </div>

        <div className="header-actions">
          <button className="btn btn-secondary btn-sm" onClick={refreshAllData} disabled={loading}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Refresh
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setOnboardingOpen(true)}>
            <Plus size={15} /> Onboard Company
          </button>
          <div className="user-profile-widget">
            <div className="user-avatar-small">SA</div>
            <div className="user-meta-small">
              <span className="user-name-small">{user?.full_name || "Super Admin"}</span>
              <span className="user-email-small">{user?.email}</span>
            </div>
            <button className="btn-icon btn-logout" onClick={logout} title="Sign Out">
              <Power size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area with Navigation Tabs */}
      <main className="super-admin-main">
        <div className="admin-tabs-nav">
          <button
            className={`admin-tab-btn ${activeTab === "overview" ? "active" : ""}`}
            onClick={() => setActiveTab("overview")}
          >
            <TrendingUp size={16} /> Platform Overview
          </button>
          <button
            className={`admin-tab-btn ${activeTab === "companies" ? "active" : ""}`}
            onClick={() => setActiveTab("companies")}
          >
            <Building2 size={16} /> Client Companies ({companies.length})
          </button>
          <button
            className={`admin-tab-btn ${activeTab === "users" ? "active" : ""}`}
            onClick={() => setActiveTab("users")}
          >
            <Users size={16} /> All Platform Users ({users.length})
          </button>
          <button
            className={`admin-tab-btn ${activeTab === "logs" ? "active" : ""}`}
            onClick={() => {
              setSelectedCompanyForLogs(null);
              setActiveTab("logs");
            }}
          >
            <Activity size={16} /> Full Audit Trail
          </button>
        </div>

        {error ? <div className="notice error my-4">{error}</div> : null}

        {/* TAB 1: OVERVIEW */}
        {activeTab === "overview" && (
          <div className="admin-tab-content">
            {/* KPI Cards Grid */}
            <div className="kpi-grid">
              <div className="kpi-card">
                <div className="kpi-icon-wrap bg-indigo">
                  <Building2 size={24} />
                </div>
                <div className="kpi-info">
                  <span className="kpi-label">Active Companies</span>
                  <h3 className="kpi-value">{stats?.active_companies || 0}</h3>
                  <span className="kpi-subtext">Total onboarded: {stats?.total_companies || 0}</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-icon-wrap bg-emerald">
                  <Users size={24} />
                </div>
                <div className="kpi-info">
                  <span className="kpi-label">Total Users</span>
                  <h3 className="kpi-value">{stats?.total_users || 0}</h3>
                  <span className="kpi-subtext">Admins & Interviewers</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-icon-wrap bg-cyan">
                  <FileText size={24} />
                </div>
                <div className="kpi-info">
                  <span className="kpi-label">Resumes Processed</span>
                  <h3 className="kpi-value">{stats?.total_candidates || 0}</h3>
                  <span className="kpi-subtext">Across all tenants</span>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-icon-wrap bg-violet">
                  <Activity size={24} />
                </div>
                <div className="kpi-info">
                  <span className="kpi-label">AI Interviews</span>
                  <h3 className="kpi-value">{stats?.total_interviews || 0}</h3>
                  <span className="kpi-subtext">HR & Tech rounds completed</span>
                </div>
              </div>
            </div>

            {/* Quick Companies Summary */}
            <div className="card mt-6">
              <div className="card-header-flex">
                <div className="card-title-group">
                  <Building2 size={18} className="text-primary" />
                  <h3 className="card-title">Recent Companies</h3>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab("companies")}>
                  View All ({companies.length})
                </button>
              </div>

              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Plan Tier</th>
                      <th>Seats Used</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.slice(0, 5).map((comp) => (
                      <tr key={comp._id}>
                        <td>
                          <div className="company-cell">
                            <span className="company-name font-semibold">{comp.name}</span>
                            <span className="company-email text-xs text-muted">{comp.contact_email}</span>
                          </div>
                        </td>
                        <td>
                          <span className="badge plan-badge">{comp.plan?.toUpperCase()}</span>
                        </td>
                        <td>
                          <span className="text-sm">
                            {comp.current_users || 1} / {comp.max_users || 5}
                          </span>
                        </td>
                        <td>
                          <span className={`badge status-badge ${comp.status === "active" ? "status-active" : "status-suspended"}`}>
                            {comp.status === "active" ? "Active" : "Suspended"}
                          </span>
                        </td>
                        <td className="text-muted text-xs">
                          {comp.created_at ? new Date(comp.created_at).toLocaleDateString() : "-"}
                        </td>
                        <td>
                          <div className="flex-row gap-2">
                            <button
                              className="btn btn-secondary btn-xs"
                              onClick={() => handleViewCompanyLogs(comp._id)}
                            >
                              Logs
                            </button>
                            <button
                              className={`btn btn-xs ${comp.status === "active" ? "btn-danger" : "btn-primary"}`}
                              onClick={() => handleToggleCompanyStatus(comp._id, comp.status)}
                            >
                              {comp.status === "active" ? "Suspend" : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: COMPANIES LIST */}
        {activeTab === "companies" && (
          <div className="admin-tab-content card">
            <div className="card-header-flex">
              <div className="card-title-group">
                <Building2 size={20} className="text-primary" />
                <h2 className="card-title">All Client Companies</h2>
              </div>
              <div className="flex-row gap-3">
                <div className="search-wrap">
                  <Search size={15} className="search-icon" />
                  <input
                    type="text"
                    className="input-field input-sm"
                    placeholder="Search company or email..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <button className="btn btn-primary btn-sm" onClick={() => setOnboardingOpen(true)}>
                  <Plus size={15} /> Onboard Company
                </button>
              </div>
            </div>

            <div className="table-responsive mt-4">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Company Name</th>
                    <th>Industry</th>
                    <th>Contact Info</th>
                    <th>Plan Tier</th>
                    <th>User Seats</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCompanies.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-8 text-muted">
                        No companies found. Click "Onboard Company" to create one.
                      </td>
                    </tr>
                  ) : (
                    filteredCompanies.map((comp) => (
                      <tr key={comp._id}>
                        <td>
                          <div className="company-cell">
                            <span className="font-semibold text-white">{comp.name}</span>
                            <span className="text-xs text-muted font-mono">{comp._id}</span>
                          </div>
                        </td>
                        <td>{comp.industry || "General"}</td>
                        <td>
                          <div className="contact-cell text-sm">
                            <div>{comp.contact_email}</div>
                            {comp.contact_phone && <div className="text-xs text-muted">{comp.contact_phone}</div>}
                          </div>
                        </td>
                        <td>
                          <span className="badge plan-badge">{comp.plan?.toUpperCase()}</span>
                        </td>
                        <td>
                          <div className="seat-progress">
                            <span className="seat-count">
                              {comp.current_users || 1} / {comp.max_users || 5}
                            </span>
                            <div className="progress-bar-bg">
                              <div
                                className="progress-bar-fill"
                                style={{
                                  width: `${Math.min(100, (((comp.current_users || 1) / (comp.max_users || 5)) * 100))}%`,
                                }}
                              />
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`badge status-badge ${comp.status === "active" ? "status-active" : "status-suspended"}`}>
                            {comp.status === "active" ? "Active" : "Suspended"}
                          </span>
                        </td>
                        <td>
                          <div className="flex-row gap-2">
                            <button
                              className="btn btn-secondary btn-xs"
                              onClick={() => handleViewCompanyLogs(comp._id)}
                              title="Inspect company activity logs"
                            >
                              Audit Logs
                            </button>
                            <button
                              className={`btn btn-xs ${comp.status === "active" ? "btn-danger" : "btn-primary"}`}
                              onClick={() => handleToggleCompanyStatus(comp._id, comp.status)}
                            >
                              {comp.status === "active" ? "Suspend" : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 3: PLATFORM USERS */}
        {activeTab === "users" && (
          <div className="admin-tab-content card">
            <div className="card-header-flex">
              <div className="card-title-group">
                <Users size={20} className="text-primary" />
                <h2 className="card-title">All Platform Users</h2>
              </div>
              <div className="search-wrap">
                <Search size={15} className="search-icon" />
                <input
                  type="text"
                  className="input-field input-sm"
                  placeholder="Search by name, email, or role..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>

            <div className="table-responsive mt-4">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Full Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Company ID</th>
                    <th>Status</th>
                    <th>Logins</th>
                    <th>Last Login</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center py-8 text-muted">
                        No users found.
                      </td>
                    </tr>
                  ) : (
                    filteredUsers.map((u) => (
                      <tr key={u._id}>
                        <td className="font-semibold text-white">{u.full_name}</td>
                        <td className="font-mono text-sm">{u.email}</td>
                        <td>
                          <span
                            className={`badge ${
                              u.role === "super_admin"
                                ? "role-badge-super"
                                : u.role === "company_admin"
                                ? "role-badge-company"
                                : "role-badge-user"
                            }`}
                          >
                            {u.role === "super_admin"
                              ? "Super Admin"
                              : u.role === "company_admin"
                              ? "Company Admin"
                              : "HR Staff"}
                          </span>
                        </td>
                        <td className="font-mono text-xs text-muted">{u.company_id || "Platform"}</td>
                        <td>
                          <span className={`badge status-badge ${u.status === "active" ? "status-active" : "status-suspended"}`}>
                            {u.status === "active" ? "Active" : "Suspended"}
                          </span>
                        </td>
                        <td>{u.login_count || 0}</td>
                        <td className="text-xs text-muted">
                          {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                        </td>
                        <td>
                          {u.role !== "super_admin" && (
                            <button
                              className={`btn btn-xs ${u.status === "active" ? "btn-danger" : "btn-primary"}`}
                              onClick={() => handleToggleUserStatus(u._id, u.status)}
                            >
                              {u.status === "active" ? "Suspend" : "Activate"}
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
        )}

        {/* TAB 4: ACTIVITY LOGS */}
        {activeTab === "logs" && (
          <div className="admin-tab-content">
            <ActivityLogViewer initialCompanyId={selectedCompanyForLogs} companies={companies} />
          </div>
        )}
      </main>

      {/* Company Onboarding Modal */}
      <CompanyOnboardingModal
        isOpen={onboardingOpen}
        onClose={() => setOnboardingOpen(false)}
        onCompanyCreated={refreshAllData}
      />
    </div>
  );
}
