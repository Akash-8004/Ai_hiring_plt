import React, { useEffect, useRef, useState } from "react";
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
  ChevronDown,
  ChevronRight,
  Key,
  Copy,
  Eye,
  EyeOff,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";
import { useAuth } from "../../hooks/useAuth";
import { CompanyOnboardingModal } from "./CompanyOnboardingModal";
import { ActivityLogViewer } from "./ActivityLogViewer";

const PLAN_TIERS = [
  { id: "starter", label: "Starter", max_users: 5, max_jobs: 3, max_credits: 500, price: null },
  { id: "growth", label: "Growth", max_users: 15, max_jobs: 10, max_credits: 2000, price: null },
  { id: "enterprise", label: "Enterprise", max_users: 50, max_jobs: 50, max_credits: 10000, price: null },
];

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
  const [companyFilter, setCompanyFilter] = useState("");
  const [expandedCompanyId, setExpandedCompanyId] = useState(null);
  const [expandedUsers, setExpandedUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [draftPlan, setDraftPlan] = useState("starter");
  const [planUpdating, setPlanUpdating] = useState(false);
  const [resetPasswordUserId, setResetPasswordUserId] = useState(null);
  const [newPasswordInput, setNewPasswordInput] = useState("");
  const [resetPasswordLoading, setResetPasswordLoading] = useState(false);
  const [resetPasswordSuccess, setResetPasswordSuccess] = useState(null);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const resetPasswordInputRef = useRef(null);
  const [planPricing, setPlanPricing] = useState({ starter: null, growth: null, enterprise: null });
  const [draftPricing, setDraftPricing] = useState({ starter: "", growth: "", enterprise: "" });
  const [pricingSaving, setPricingSaving] = useState(false);
  const [companyUsage, setCompanyUsage] = useState(null);
  const [usagePage, setUsagePage] = useState(1);
  const [creditAdjustAmount, setCreditAdjustAmount] = useState("");
  const [creditAdjustLoading, setCreditAdjustLoading] = useState(false);
  const [companyDrives, setCompanyDrives] = useState(null);

  useEffect(() => {
    if (resetPasswordUserId && !resetPasswordSuccess && resetPasswordInputRef.current) {
      const timer = setTimeout(() => resetPasswordInputRef.current?.focus(), 0);
      return () => clearTimeout(timer);
    }
  }, [resetPasswordUserId, resetPasswordSuccess]);

  const refreshAllData = async () => {
    setLoading(true);
    setError("");
    try {
      const [statsData, companiesData, usersData, pricingData] = await Promise.all([
        apiFetchJson("/api/admin/stats"),
        apiFetchJson("/api/admin/companies"),
        apiFetchJson("/api/admin/users"),
        apiFetchJson("/api/admin/plans/pricing"),
      ]);
      setStats(statsData);
      setCompanies(companiesData.companies || []);
      setUsers(usersData.users || []);
      setPlanPricing(pricingData);
      setDraftPricing({
        starter: pricingData.starter != null ? String(pricingData.starter) : "",
        growth: pricingData.growth != null ? String(pricingData.growth) : "",
        enterprise: pricingData.enterprise != null ? String(pricingData.enterprise) : "",
      });
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

  const handleDeleteUser = async (u) => {
    const cascades = u.role === "company_admin" && !!u.company_id;
    const warn = cascades
      ? `Deleting this company admin will also permanently remove every sub-user in their company. This cannot be undone.`
      : `This will permanently delete this user. This cannot be undone.`;
    if (!window.confirm(`Delete ${u.full_name} (${u.email})?\n\n${warn}`)) return;
    try {
      await apiFetchJson(`/api/admin/users/${u._id}`, { method: "DELETE" });
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to delete user.");
    }
  };

  const handleDeleteCompany = async (comp) => {
    const confirmed = window.prompt(
      `Permanently delete company "${comp.name}"?\n\nThis removes the company and ALL of its data (users, candidates, jobs, usage records). This cannot be undone.\n\nType the exact company name to confirm:`,
      ""
    );
    if (confirmed === null) return;
    if (confirmed.trim() !== comp.name) {
      alert("Company name did not match. Deletion cancelled.");
      return;
    }
    try {
      await apiFetchJson(`/api/admin/companies/${comp._id}`, { method: "DELETE" });
      if (expandedCompanyId === comp._id) {
        setExpandedCompanyId(null);
        setCompanyUsage(null);
      setCompanyDrives(null);
      }
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to delete company.");
    }
  };

  const handleViewCompanyLogs = (companyId) => {
    setSelectedCompanyForLogs(companyId);
    setActiveTab("logs");
  };

  const handleToggleExpand = async (comp) => {
    if (expandedCompanyId === comp._id) {
      setExpandedCompanyId(null);
      setCompanyUsage(null);
      setCompanyDrives(null);
      setResetPasswordUserId(null);
      setNewPasswordInput("");
      setResetPasswordSuccess(null);
      setShowNewPassword(false);
      return;
    }
    setExpandedCompanyId(comp._id);
    setDraftPlan(comp.plan || "starter");
    setExpandedUsers([]);
    setCompanyUsage(null);
    setCompanyDrives(null);
    setUsagePage(1);
    setLoadingUsers(true);
    try {
      const [usersData, usageData, drivesData] = await Promise.all([
        apiFetchJson(`/api/admin/companies/${comp._id}/users`),
        apiFetchJson(`/api/admin/companies/${comp._id}/usage?page=1&limit=10`),
        apiFetchJson(`/api/admin/companies/${comp._id}/drives`),
      ]);
      setExpandedUsers(usersData.users || []);
      setCompanyUsage(usageData);
      setCompanyDrives(drivesData);
    } catch (err) {
      setError(err.message || "Failed to load company details.");
    } finally {
      setLoadingUsers(false);
    }
  };

  const loadCompanyUsage = async (companyId, page = 1) => {
    try {
      const usageData = await apiFetchJson(`/api/admin/companies/${companyId}/usage?page=${page}&limit=10`);
      setCompanyUsage(usageData);
      setUsagePage(page);
    } catch (err) {
      alert(err.message || "Failed to load usage data.");
    }
  };

  const handleAdjustCredits = async (companyId, delta) => {
    if (!delta) return;
    setCreditAdjustLoading(true);
    try {
      await apiFetchJson(`/api/admin/companies/${companyId}/credits`, {
        method: "POST",
        body: JSON.stringify({ delta, note: `Manual ${delta > 0 ? "add" : "remove"} by Super Admin` }),
      });
      setCreditAdjustAmount("");
      await loadCompanyUsage(companyId, usagePage);
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to adjust credits.");
    } finally {
      setCreditAdjustLoading(false);
    }
  };

  const loadCompanyDrives = async (companyId) => {
    try {
      const drivesData = await apiFetchJson(`/api/admin/companies/${companyId}/drives`);
      setCompanyDrives(drivesData);
    } catch (err) {
      alert(err.message || "Failed to load drives.");
    }
  };

  const handleDeleteDriveSa = async (companyId, drive) => {
    const count = drive.candidate_count ?? 0;
    const msg = `Delete drive "${drive.title}"? This permanently removes the drive and all ${count} of its candidates.`;
    if (!window.confirm(msg)) return;
    try {
      await apiFetchJson(
        `/api/job/${encodeURIComponent(drive.job_id)}?company_id=${encodeURIComponent(companyId)}`,
        { method: "DELETE" }
      );
      await loadCompanyDrives(companyId);
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to delete drive.");
    }
  };

  const handleSavePricing = async () => {
    setPricingSaving(true);
    try {
      const prices = {
        starter: draftPricing.starter === "" ? null : Number(draftPricing.starter),
        growth: draftPricing.growth === "" ? null : Number(draftPricing.growth),
        enterprise: draftPricing.enterprise === "" ? null : Number(draftPricing.enterprise),
      };
      const updated = await apiFetchJson("/api/admin/plans/pricing", {
        method: "PUT",
        body: JSON.stringify({ prices }),
      });
      setPlanPricing(updated);
      setDraftPricing({
        starter: updated.starter != null ? String(updated.starter) : "",
        growth: updated.growth != null ? String(updated.growth) : "",
        enterprise: updated.enterprise != null ? String(updated.enterprise) : "",
      });
    } catch (err) {
      alert(err.message || "Failed to save pricing.");
    } finally {
      setPricingSaving(false);
    }
  };

  const handleChangePlan = async (companyId) => {
    setPlanUpdating(true);
    setError("");
    try {
      await apiFetchJson(`/api/admin/companies/${companyId}`, {
        method: "PUT",
        body: JSON.stringify({ plan: draftPlan }),
      });
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to update company plan.");
    } finally {
      setPlanUpdating(false);
    }
  };

  const handleResetPassword = async (userId) => {
    if (!newPasswordInput || newPasswordInput.length < 8) {
      alert("Password must be at least 8 characters.");
      return;
    }
    const missing = [];
    if (!/[A-Z]/.test(newPasswordInput)) missing.push("uppercase letter");
    if (!/[a-z]/.test(newPasswordInput)) missing.push("lowercase letter");
    if (!/\d/.test(newPasswordInput)) missing.push("digit");
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(newPasswordInput)) missing.push("special character");
    if (missing.length) {
      alert("Password must include: " + missing.join(", "));
      return;
    }
    setResetPasswordLoading(true);
    setError("");
    try {
      const data = await apiFetchJson(`/api/admin/users/${userId}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ new_password: newPasswordInput }),
      });
      setResetPasswordSuccess({ userId, new_password: data.new_password });
      setNewPasswordInput("");
      setResetPasswordUserId(null);
      setShowNewPassword(false);
    } catch (err) {
      alert(err.message || "Failed to reset password.");
    } finally {
      setResetPasswordLoading(false);
    }
  };

  const handleCopyPassword = (password) => {
    navigator.clipboard.writeText(password).then(
      () => alert("Password copied to clipboard!"),
      () => alert("Failed to copy.")
    );
  };

  const filteredCompanies = companies.filter((c) => {
    const q = searchQuery.toLowerCase();
    return c.name.toLowerCase().includes(q) || c.contact_email.toLowerCase().includes(q) || (c.industry || "").toLowerCase().includes(q);
  });

  const filteredUsers = users.filter((u) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch = u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q) || u.role.toLowerCase().includes(q);
    if (!matchesSearch) return false;
    if (!companyFilter) return true;
    if (companyFilter === "__platform__") return !u.company_id;
    return u.company_id === companyFilter;
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
            className={`admin-tab-btn ${activeTab === "pricing" ? "active" : ""}`}
            onClick={() => setActiveTab("pricing")}
          >
            <Layers size={16} /> Plans & Pricing
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
                          {comp.created_at ? new Date(comp.created_at).toLocaleDateString(undefined, { timeZone: "UTC" }) : "-"}
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
                            <button
                              className="btn btn-xs btn-danger-ghost"
                              title="Permanently delete this company and all its data"
                              onClick={() => handleDeleteCompany(comp)}
                            >
                              Delete
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
                    autoComplete="one-time-code"
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
                    <th>Credits</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCompanies.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center py-8 text-muted">
                        No companies found. Click "Onboard Company" to create one.
                      </td>
                    </tr>
                  ) : (
                    filteredCompanies.map((comp) => (
                      <React.Fragment key={comp._id}>
                      <tr className={expandedCompanyId === comp._id ? "row-expanded" : ""}>
                        <td>
                          <button
                            className="company-name-toggle"
                            onClick={() => handleToggleExpand(comp)}
                            title="View team members & manage plan"
                          >
                            {expandedCompanyId === comp._id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                            <span className="company-cell">
                              <span className="font-semibold text-white">{comp.name}</span>
                              <span className="text-xs text-muted font-mono">{comp._id}</span>
                            </span>
                          </button>
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
                          <span className="text-sm font-mono">
                            {comp.credits
                              ? `${comp.credits.used || 0} / ${comp.credits.allowance || 0}`
                              : "—"}
                          </span>
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
                            <button
                              className="btn btn-xs btn-danger-ghost"
                              title="Permanently delete this company and all its data"
                              onClick={() => handleDeleteCompany(comp)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>

                      {expandedCompanyId === comp._id && (
                        <tr className="company-expand-row">
                          <td colSpan={8}>
                            <div className="company-expand-panel">
                              <div className="expand-section">
                                <div className="expand-section-head">
                                  <Layers size={15} /> <h4>Subscription Plan</h4>
                                </div>
                                <div className="plan-changer">
                                  {PLAN_TIERS.map((tier) => (
                                    <label
                                      key={tier.id}
                                      className={`plan-option ${draftPlan === tier.id ? "selected" : ""}`}
                                    >
                                      <input
                                        type="radio"
                                        name={`plan-${comp._id}`}
                                        value={tier.id}
                                        checked={draftPlan === tier.id}
                                        onChange={() => setDraftPlan(tier.id)}
                                      />
                                      <span className="plan-option-name">{tier.label}</span>
                                      <span className="plan-option-limits">
                                        {tier.max_users} users · {tier.max_jobs} jobs · {tier.max_credits.toLocaleString()} credits/mo
                                      </span>
                                      {planPricing[tier.id] != null && (
                                        <span className="plan-option-limits">${planPricing[tier.id]}/mo</span>
                                      )}
                                      {comp.plan === tier.id && <span className="plan-current-tag">Current</span>}
                                    </label>
                                  ))}
                                </div>
                                <button
                                  className="btn btn-primary btn-sm mt-3"
                                  onClick={() => handleChangePlan(comp._id)}
                                  disabled={planUpdating || draftPlan === comp.plan}
                                >
                                  {planUpdating
                                    ? "Updating…"
                                    : draftPlan === comp.plan
                                    ? "Current Plan"
                                    : `Change to ${PLAN_TIERS.find((t) => t.id === draftPlan)?.label}`}
                                </button>
                              </div>

                              <div className="expand-section">
                                <div className="expand-section-head">
                                  <Activity size={15} /> <h4>Credit Usage</h4>
                                </div>
                                {companyUsage?.credits ? (
                                  <>
                                    <div className="usage-stat-grid">
                                      <div>
                                        <span className="usage-stat-label">Allowance</span>
                                        <strong>{companyUsage.credits.allowance?.toLocaleString() ?? "—"}</strong>
                                      </div>
                                      <div>
                                        <span className="usage-stat-label">Used</span>
                                        <strong>{companyUsage.credits.used?.toLocaleString() ?? "—"}</strong>
                                      </div>
                                      <div>
                                        <span className="usage-stat-label">Remaining</span>
                                        <strong>{companyUsage.credits.remaining?.toLocaleString() ?? "—"}</strong>
                                      </div>
                                    </div>
                                    <div className="progress-bar-bg mt-3">
                                      <div
                                        className="progress-bar-fill"
                                        style={{
                                          width: `${companyUsage.credits.allowance ? Math.min(100, ((companyUsage.credits.used || 0) / companyUsage.credits.allowance) * 100) : 0}%`,
                                        }}
                                      />
                                    </div>
                                    <div className="flex-row gap-2 mt-3 align-center">
                                      <input
                                        type="number"
                                        className="input-field input-sm"
                                        placeholder="Minutes"
                                        value={creditAdjustAmount}
                                        onChange={(e) => setCreditAdjustAmount(e.target.value)}
                                        style={{ width: 120 }}
                                      />
                                      <button
                                        className="btn btn-primary btn-xs"
                                        disabled={creditAdjustLoading || !creditAdjustAmount}
                                        onClick={() => handleAdjustCredits(comp._id, Number(creditAdjustAmount))}
                                      >
                                        Add Credits
                                      </button>
                                      <button
                                        className="btn btn-danger btn-xs"
                                        disabled={creditAdjustLoading || !creditAdjustAmount}
                                        onClick={() => handleAdjustCredits(comp._id, -Number(creditAdjustAmount))}
                                      >
                                        Remove Credits
                                      </button>
                                    </div>
                                    <table className="sub-users-table mt-4">
                                      <thead>
                                        <tr>
                                          <th>Time</th>
                                          <th>Candidate</th>
                                          <th>Round</th>
                                          <th>Min</th>
                                          <th>Action</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {(companyUsage.usage?.entries || []).map((entry) => (
                                          <tr key={entry._id || entry.created_at}>
                                            <td className="text-xs text-muted">
                                              {entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}
                                            </td>
                                            <td className="font-mono text-xs">{entry.candidate_email || "—"}</td>
                                            <td>{entry.round_type}</td>
                                            <td>{entry.minutes}</td>
                                            <td>{entry.action}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                    {(companyUsage.usage?.total || 0) > 10 && (
                                      <div className="flex-row gap-2 mt-2">
                                        <button
                                          className="btn btn-secondary btn-xs"
                                          disabled={usagePage <= 1}
                                          onClick={() => loadCompanyUsage(comp._id, usagePage - 1)}
                                        >
                                          Prev
                                        </button>
                                        <span className="text-xs text-muted">Page {usagePage}</span>
                                        <button
                                          className="btn btn-secondary btn-xs"
                                          disabled={usagePage * 10 >= (companyUsage.usage?.total || 0)}
                                          onClick={() => loadCompanyUsage(comp._id, usagePage + 1)}
                                        >
                                          Next
                                        </button>
                                      </div>
                                    )}
                                  </>
                                ) : (
                                  <p className="text-muted text-sm">No credit data available.</p>
                                )}
                              </div>

                              <div className="expand-section">
                                <div className="expand-section-head">
                                  <Briefcase size={15} /> <h4>Job Drives & Pipeline</h4>
                                </div>
                                {companyDrives ? (
                                  <>
                                    <p className="text-sm text-muted mb-3">
                                      {companyDrives.jobs_used ?? 0} of {companyDrives.max_jobs ?? 0} drives used
                                    </p>
                                    {(companyDrives.drives || []).length === 0 ? (
                                      <p className="text-muted text-sm">No drives yet.</p>
                                    ) : (
                                      (companyDrives.drives || []).map((drive) => (
                                        <div key={drive.job_id} className="sa-drive-card">
                                          <div className="sa-drive-head">
                                            <div>
                                              <strong>{drive.title}</strong>
                                              {drive.active && <span className="badge badge-subtle ml-2">Active</span>}
                                              <p className="text-xs text-muted">
                                                {drive.department} · {drive.location} · {drive.experience_years}+ yrs
                                                {drive.created_at ? ` · ${new Date(drive.created_at).toLocaleDateString()}` : ""}
                                              </p>
                                            </div>
                                            <button
                                              type="button"
                                              className="btn btn-danger btn-xs"
                                              onClick={() => handleDeleteDriveSa(comp._id, drive)}
                                            >
                                              Delete Drive
                                            </button>
                                          </div>
                                          <div className="usage-stat-grid mt-2">
                                            <div><span className="usage-stat-label">Uploaded</span><strong>{drive.metrics?.uploaded ?? 0}</strong></div>
                                            <div><span className="usage-stat-label">Shortlisted</span><strong>{drive.metrics?.shortlisted ?? 0}</strong></div>
                                            <div><span className="usage-stat-label">HR Passed</span><strong>{drive.metrics?.hrPassed ?? 0}</strong></div>
                                            <div><span className="usage-stat-label">Tech Passed</span><strong>{drive.metrics?.techPassed ?? 0}</strong></div>
                                            <div><span className="usage-stat-label">Hired</span><strong>{drive.metrics?.hired ?? 0}</strong></div>
                                            <div><span className="usage-stat-label">Avg Score</span><strong>{drive.metrics?.averageScore ?? 0}%</strong></div>
                                          </div>
                                          <p className="text-xs text-muted mt-2">{drive.candidate_count ?? 0} candidates</p>
                                        </div>
                                      ))
                                    )}
                                  </>
                                ) : (
                                  <p className="text-muted text-sm">Loading drives…</p>
                                )}
                              </div>

                              <div className="expand-section">
                                <div className="expand-section-head">
                                  <Users size={15} /> <h4>Team Members ({loadingUsers ? "…" : expandedUsers.length})</h4>
                                </div>
                                {loadingUsers ? (
                                  <p className="text-muted text-sm">Loading team members…</p>
                                ) : expandedUsers.length === 0 ? (
                                  <p className="text-muted text-sm">No team members found for this company.</p>
                                ) : (
                                  <>
                                  <table className="sub-users-table">
                                    <thead>
                                      <tr>
                                        <th>Name</th>
                                        <th>Email</th>
                                        <th>Role</th>
                                        <th>Status</th>
                                        <th>Last Login</th>
                                        <th>Update Credential</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {expandedUsers.map((su) => (
                                        <tr key={su._id}>
                                          <td className="font-semibold">{su.full_name}</td>
                                          <td className="font-mono text-xs">{su.email}</td>
                                          <td>
                                            <span className={`badge ${su.role === "company_admin" ? "role-badge-company" : "role-badge-user"}`}>
                                              {su.role === "company_admin" ? "Company Admin" : "HR / Interviewer"}
                                            </span>
                                          </td>
                                          <td>
                                            <span className={`badge status-badge ${su.status === "active" ? "status-active" : "status-suspended"}`}>
                                              {su.status === "active" ? "Active" : "Suspended"}
                                            </span>
                                          </td>
                                          <td className="text-xs text-muted">
                                            {su.last_login ? new Date(su.last_login).toLocaleString(undefined, { timeZone: "UTC" }) : "Never"}
                                          </td>
                                          <td>
                                            {su.role === "super_admin" ? (
                                              <span className="text-xs text-muted">—</span>
                                            ) : (
                                              <button
                                                className={`btn btn-xs ${resetPasswordUserId === su._id ? "btn-primary" : "btn-secondary"}`}
                                                onClick={() => {
                                                  setResetPasswordUserId(resetPasswordUserId === su._id ? null : su._id);
                                                  setNewPasswordInput("");
                                                  setShowNewPassword(false);
                                                  setResetPasswordSuccess(null);
                                                }}
                                                title="Reset password for this user"
                                              >
                                                <Key size={12} /> {resetPasswordUserId === su._id ? "Cancel" : "Reset"}
                                              </button>
                                            )}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>

                                  {resetPasswordSuccess && (
                                    <div className="reset-password-panel">
                                      <div className="credentials-box">
                                        <div className="credential-row">
                                          <span className="label">Email</span>
                                          <span className="value font-mono">
                                            {expandedUsers.find((u) => u._id === resetPasswordSuccess.userId)?.email}
                                          </span>
                                        </div>
                                        <div className="credential-row">
                                          <span className="label">New Password</span>
                                          <div className="password-display-row">
                                            <span className="value font-mono">
                                              {showNewPassword ? resetPasswordSuccess.new_password : "••••••••"}
                                            </span>
                                            <button
                                              className="btn btn-secondary btn-xs"
                                              onClick={() => setShowNewPassword(!showNewPassword)}
                                            >
                                              {showNewPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                                            </button>
                                            <button
                                              className="btn btn-secondary btn-xs"
                                              onClick={() => handleCopyPassword(resetPasswordSuccess.new_password)}
                                            >
                                              <Copy size={13} /> Copy
                                            </button>
                                          </div>
                                        </div>
                                        <p className="text-xs text-muted mt-2">
                                          Share this new password with the team member. It will not be shown again.
                                        </p>
                                      </div>
                                      <button
                                        className="btn btn-secondary btn-xs mt-2"
                                        onClick={() => setResetPasswordSuccess(null)}
                                      >
                                        Dismiss
                                      </button>
                                    </div>
                                  )}

                                  {resetPasswordUserId && !resetPasswordSuccess && (
                                    <div className="reset-password-panel">
                                      <div className="expand-section-head" style={{ marginBottom: 8 }}>
                                        <Key size={13} />
                                        <h4>
                                          Reset Password for {expandedUsers.find((u) => u._id === resetPasswordUserId)?.full_name}
                                        </h4>
                                      </div>
                                      <div className="flex-row gap-2 align-center">
                                        <input
                                          ref={resetPasswordInputRef}
                                          type={showNewPassword ? "text" : "password"}
                                          className="input-field input-sm"
                                          placeholder="New password (min 8 chars)"
                                          value={newPasswordInput}
                                          onChange={(e) => setNewPasswordInput(e.target.value)}
                                          onKeyDown={(e) => {
                                            if (e.key === "Enter") handleResetPassword(resetPasswordUserId);
                                            if (e.key === "Escape") {
                                              setResetPasswordUserId(null);
                                              setNewPasswordInput("");
                                              setShowNewPassword(false);
                                            }
                                          }}
                                          autoComplete="new-password"
                                          style={{ flex: 1 }}
                                        />
                                        <button
                                          className="btn btn-secondary btn-xs"
                                          onClick={() => setShowNewPassword(!showNewPassword)}
                                        >
                                          {showNewPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                                        </button>
                                        <button
                                          className="btn btn-primary btn-xs"
                                          onClick={() => handleResetPassword(resetPasswordUserId)}
                                          disabled={resetPasswordLoading || newPasswordInput.length < 8}
                                        >
                                          {resetPasswordLoading ? "Setting…" : "Set Password"}
                                        </button>
                                        <button
                                          className="btn btn-secondary btn-xs"
                                          onClick={() => {
                                            setResetPasswordUserId(null);
                                            setNewPasswordInput("");
                                            setShowNewPassword(false);
                                          }}
                                        >
                                          Cancel
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                  </>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                      </React.Fragment>
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
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <select
                  className="select-field"
                  value={companyFilter}
                  onChange={(e) => setCompanyFilter(e.target.value)}
                >
                  <option value="">All Companies</option>
                  {companies.map((c) => (
                    <option key={c._id} value={c._id}>{c.name}</option>
                  ))}
                  <option value="__platform__">Platform (No Company)</option>
                </select>
                <div className="search-wrap">
                  <Search size={15} className="search-icon" />
                  <input
                    type="text"
                    className="input-field input-sm"
                    placeholder="Search by name, email, or role..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    autoComplete="one-time-code"
                  />
                </div>
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
                          {u.last_login ? new Date(u.last_login).toLocaleString(undefined, { timeZone: "UTC" }) : "Never"}
                        </td>
                        <td>
                          {u.role !== "super_admin" && (
                            <div className="action-group">
                              <button
                                className={`btn btn-xs ${u.status === "active" ? "btn-danger" : "btn-primary"}`}
                                onClick={() => handleToggleUserStatus(u._id, u.status)}
                              >
                                {u.status === "active" ? "Suspend" : "Activate"}
                              </button>
                              <button
                                className="btn btn-xs btn-danger-ghost"
                                title="Permanently delete this user"
                                onClick={() => handleDeleteUser(u)}
                              >
                                Delete
                              </button>
                            </div>
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

        {activeTab === "pricing" && (
          <div className="admin-tab-content card">
            <div className="card-header-flex">
              <div className="card-title-group">
                <Layers size={20} className="text-primary" />
                <h2 className="card-title">Plans & Pricing</h2>
              </div>
            </div>
            <p className="text-sm text-muted mt-2">
              Set monthly USD prices for each plan tier. Leave empty for &quot;Not set&quot;.
            </p>
            <div className="plan-pricing-grid mt-4">
              {PLAN_TIERS.map((tier) => (
                <div key={tier.id} className="plan-pricing-row">
                  <div>
                    <strong>{tier.label}</strong>
                    <p className="text-xs text-muted">
                      {tier.max_users} users · {tier.max_jobs} jobs · {tier.max_credits.toLocaleString()} credits/mo
                    </p>
                  </div>
                  <div className="flex-row gap-2 align-center">
                    <span className="text-muted">$</span>
                    <input
                      type="number"
                      className="input-field input-sm"
                      placeholder="Not set"
                      value={draftPricing[tier.id]}
                      onChange={(e) => setDraftPricing({ ...draftPricing, [tier.id]: e.target.value })}
                      min="0"
                      step="0.01"
                    />
                    <span className="text-muted text-sm">/mo</span>
                  </div>
                </div>
              ))}
            </div>
            <button className="btn btn-primary btn-sm mt-4" onClick={handleSavePricing} disabled={pricingSaving}>
              {pricingSaving ? "Saving…" : "Save Pricing"}
            </button>
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
