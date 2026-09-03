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
  Inbox,
  Mail,
  Loader2,
  Pencil,
  Archive,
  RotateCcw,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";
import { useAuth } from "../../hooks/useAuth";
import { CompanyOnboardingModal } from "./CompanyOnboardingModal";
import { ActivityLogViewer } from "./ActivityLogViewer";
import { LeadsPanel } from "./LeadsPanel";

const PLAN_TIERS = [
  { id: "starter", label: "Starter", max_users: 5, max_candidates: 100, max_credits: 500, price: null },
  { id: "growth", label: "Growth", max_users: 15, max_candidates: 500, max_credits: 2000, price: null },
  { id: "enterprise", label: "Enterprise", max_users: 50, max_candidates: 5000, max_credits: 10000, price: null },
];

export function SuperAdminDashboard() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [newLeadCount, setNewLeadCount] = useState(0);
  const [onboardingLead, setOnboardingLead] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [selectedCompanyForLogs, setSelectedCompanyForLogs] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [credentialEmailSending, setCredentialEmailSending] = useState(false);
  const [credentialEmailSent, setCredentialEmailSent] = useState(null);
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
  const [draftPlans, setDraftPlans] = useState({
    starter: { price: "", max_users: "5", max_candidates: "100" },
    growth: { price: "", max_users: "15", max_candidates: "500" },
    enterprise: { price: "", max_users: "50", max_candidates: "5000" },
  });
  const [pricingSaving, setPricingSaving] = useState(false);
  const [companyUsage, setCompanyUsage] = useState(null);
  const [usagePage, setUsagePage] = useState(1);
  const [creditAdjustAmount, setCreditAdjustAmount] = useState("");
  const [creditAdjustLoading, setCreditAdjustLoading] = useState(false);
  const [companyDrives, setCompanyDrives] = useState(null);
  const [editingUserId, setEditingUserId] = useState(null);
  const [editUserForm, setEditUserForm] = useState({ full_name: "", email: "", role: "sub_user" });
  const [editUserLoading, setEditUserLoading] = useState(false);
  const [companyViewMode, setCompanyViewMode] = useState("active");
  const [archivedCompanies, setArchivedCompanies] = useState([]);
  const [loadingArchived, setLoadingArchived] = useState(false);

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
      const [statsData, companiesData, usersData, pricingData, leadsData] = await Promise.all([
        apiFetchJson("/api/admin/stats"),
        apiFetchJson("/api/admin/companies"),
        apiFetchJson("/api/admin/users"),
        apiFetchJson("/api/admin/plans/pricing"),
        apiFetchJson("/api/admin/leads?status=new&limit=1").catch(() => ({ total: 0 })),
      ]);
      setStats(statsData);
      setCompanies(companiesData.companies || []);
      setUsers(usersData.users || []);
      setNewLeadCount(leadsData.total || 0);
      setPlanPricing(pricingData);
      setDraftPlans({
        starter: {
          price: pricingData.starter?.price != null ? String(pricingData.starter.price) : "",
          max_users: String(pricingData.starter?.max_users ?? 5),
          max_candidates: String(pricingData.starter?.max_candidates ?? 100),
        },
        growth: {
          price: pricingData.growth?.price != null ? String(pricingData.growth.price) : "",
          max_users: String(pricingData.growth?.max_users ?? 15),
          max_candidates: String(pricingData.growth?.max_candidates ?? 500),
        },
        enterprise: {
          price: pricingData.enterprise?.price != null ? String(pricingData.enterprise.price) : "",
          max_users: String(pricingData.enterprise?.max_users ?? 50),
          max_candidates: String(pricingData.enterprise?.max_candidates ?? 5000),
        },
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
      `Archive company "${comp.name}"?\n\nThis will archive the company, suspend its team members, and hide it from active lists. Data is preserved and can be restored later.\n\nType the exact company name to confirm:`,
      ""
    );
    if (confirmed === null) return;
    if (confirmed.trim() !== comp.name) {
      alert("Company name did not match. Archival cancelled.");
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
      if (companyViewMode === "archived") {
        await loadArchivedCompanies();
      }
    } catch (err) {
      alert(err.message || "Failed to archive company.");
    }
  };

  const loadArchivedCompanies = async () => {
    setLoadingArchived(true);
    try {
      const res = await apiFetchJson("/api/admin/companies/archived");
      setArchivedCompanies(res.companies || []);
    } catch (err) {
      alert(err.message || "Failed to load archived companies.");
    } finally {
      setLoadingArchived(false);
    }
  };

  const handleRestoreCompany = async (comp) => {
    if (!window.confirm(`Restore company "${comp.name}" back to active status? Its team members will also be reactivated.`)) return;
    try {
      await apiFetchJson(`/api/admin/companies/${comp._id}/restore`, { method: "POST" });
      await refreshAllData();
      await loadArchivedCompanies();
    } catch (err) {
      alert(err.message || "Failed to restore company.");
    }
  };

  const handleSaveEditUser = async (userId) => {
    if (!editUserForm.full_name?.trim()) {
      alert("Full name is required.");
      return;
    }
    if (!editUserForm.email?.trim()) {
      alert("Email is required.");
      return;
    }
    setEditUserLoading(true);
    try {
      const res = await apiFetchJson(`/api/admin/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify(editUserForm),
      });
      if (res.ok && res.user) {
        setExpandedUsers((prev) =>
          prev.map((u) => (u._id === userId ? { ...u, ...res.user } : u))
        );
      }
      setEditingUserId(null);
      await refreshAllData();
    } catch (err) {
      alert(err.message || "Failed to update user profile.");
    } finally {
      setEditUserLoading(false);
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
      setEditingUserId(null);
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
      const plans = {};
      for (const tier of PLAN_TIERS) {
        const draft = draftPlans[tier.id];
        plans[tier.id] = {
          price: draft.price === "" ? null : Number(draft.price),
          max_users: Number(draft.max_users),
          max_candidates: Number(draft.max_candidates),
        };
      }
      const updated = await apiFetchJson("/api/admin/plans/pricing", {
        method: "PUT",
        body: JSON.stringify({ plans }),
      });
      setPlanPricing(updated);
      setDraftPlans({
        starter: {
          price: updated.starter?.price != null ? String(updated.starter.price) : "",
          max_users: String(updated.starter?.max_users ?? 5),
          max_candidates: String(updated.starter?.max_candidates ?? 100),
        },
        growth: {
          price: updated.growth?.price != null ? String(updated.growth.price) : "",
          max_users: String(updated.growth?.max_users ?? 15),
          max_candidates: String(updated.growth?.max_candidates ?? 500),
        },
        enterprise: {
          price: updated.enterprise?.price != null ? String(updated.enterprise.price) : "",
          max_users: String(updated.enterprise?.max_users ?? 50),
          max_candidates: String(updated.enterprise?.max_candidates ?? 5000),
        },
      });
    } catch (err) {
      alert(err.message || "Failed to save plan settings.");
    } finally {
      setPricingSaving(false);
    }
  };

  const updateDraftPlan = (tierId, field, value) => {
    setDraftPlans((prev) => ({
      ...prev,
      [tierId]: { ...prev[tierId], [field]: value },
    }));
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

  const handleConvertLead = (lead) => {
    setOnboardingLead(lead);
    setOnboardingOpen(true);
  };

  const handleOnboardingClose = () => {
    setOnboardingOpen(false);
    setOnboardingLead(null);
  };

  const displayedCompanyList = companyViewMode === "archived" ? archivedCompanies : companies;
  const filteredCompanies = displayedCompanyList.filter((c) => {
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
            className={`admin-tab-btn ${activeTab === "leads" ? "active" : ""}`}
            onClick={() => setActiveTab("leads")}
          >
            <Inbox size={16} /> Leads {newLeadCount > 0 ? `(${newLeadCount})` : ""}
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
                  <span className="kpi-subtext">Total: {stats?.total_companies || 0} · Archived: {stats?.archived_companies || 0}</span>
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
                <h2 className="card-title">Client Companies</h2>
                <div className="flex-row gap-2 ml-4">
                  <button
                    className={`btn btn-xs ${companyViewMode === "active" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setCompanyViewMode("active")}
                  >
                    Active ({companies.length})
                  </button>
                  <button
                    className={`btn btn-xs ${companyViewMode === "archived" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => {
                      setCompanyViewMode("archived");
                      loadArchivedCompanies();
                    }}
                  >
                    <Archive size={12} /> Archived ({stats?.archived_companies ?? archivedCompanies.length})
                  </button>
                </div>
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
                        {loadingArchived
                          ? "Loading archived companies…"
                          : companyViewMode === "archived"
                          ? "No archived companies found."
                          : 'No companies found. Click "Onboard Company" to create one.'}
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
                          <span className={`badge status-badge ${comp.status === "active" ? "status-active" : comp.status === "archived" ? "status-suspended" : "status-suspended"}`}>
                            {comp.status === "active" ? "Active" : comp.status === "archived" ? "Archived" : "Suspended"}
                          </span>
                        </td>
                        <td>
                          {companyViewMode === "archived" ? (
                            <div className="flex-row gap-2">
                              <button
                                className="btn btn-primary btn-xs"
                                title="Restore this company and its team members"
                                onClick={() => handleRestoreCompany(comp)}
                              >
                                <RotateCcw size={12} /> Restore
                              </button>
                            </div>
                          ) : (
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
                                title="Archive this company (soft delete)"
                                onClick={() => handleDeleteCompany(comp)}
                              >
                                Archive
                              </button>
                            </div>
                          )}
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
                                        {(planPricing[tier.id]?.max_users ?? tier.max_users)} users · {(planPricing[tier.id]?.max_candidates ?? tier.max_candidates)} candidates · {tier.max_credits.toLocaleString()} credits/mo
                                      </span>
                                      {planPricing[tier.id]?.price != null && (
                                        <span className="plan-option-limits">${planPricing[tier.id].price}/mo</span>
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
                                      {companyDrives.jobs_used ?? 0} job drive{companyDrives.jobs_used === 1 ? "" : "s"} (unrestricted)
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
                                        <th>Actions</th>
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
                                              <div className="flex-row gap-1 align-center">
                                                <button
                                                  className={`btn btn-xs ${editingUserId === su._id ? "btn-primary" : "btn-secondary"}`}
                                                  onClick={() => {
                                                    if (editingUserId === su._id) {
                                                      setEditingUserId(null);
                                                    } else {
                                                      setEditingUserId(su._id);
                                                      setEditUserForm({
                                                        full_name: su.full_name || "",
                                                        email: su.email || "",
                                                        role: su.role || "sub_user",
                                                      });
                                                      setResetPasswordUserId(null);
                                                    }
                                                  }}
                                                  title="Edit team member details"
                                                >
                                                  <Pencil size={12} /> {editingUserId === su._id ? "Cancel" : "Edit"}
                                                </button>
                                                <button
                                                  className={`btn btn-xs ${resetPasswordUserId === su._id ? "btn-primary" : "btn-secondary"}`}
                                                  onClick={() => {
                                                    setResetPasswordUserId(resetPasswordUserId === su._id ? null : su._id);
                                                    setNewPasswordInput("");
                                                    setShowNewPassword(false);
                                                    setResetPasswordSuccess(null);
                                                    setEditingUserId(null);
                                                  }}
                                                  title="Reset password for this user"
                                                >
                                                  <Key size={12} /> {resetPasswordUserId === su._id ? "Cancel" : "Reset"}
                                                </button>
                                              </div>
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
                                            <button
                                              className={`btn btn-secondary btn-xs ${credentialEmailSent === "sent" ? "email-send-btn sent" : credentialEmailSent === "failed" ? "email-send-btn failed" : ""}`}
                                              disabled={credentialEmailSending || credentialEmailSent === "sent"}
                                              onClick={async () => {
                                                const targetUser = expandedUsers.find((u) => u._id === resetPasswordSuccess.userId);
                                                if (!targetUser) return;
                                                const companyId = targetUser.company_id;
                                                if (!companyId) return alert("No company associated");
                                                setCredentialEmailSending(true);
                                                setCredentialEmailSent(null);
                                                try {
                                                  const res = await apiFetchJson(
                                                    `/api/admin/companies/${companyId}/send-credentials`,
                                                    {
                                                      method: "POST",
                                                      body: JSON.stringify({
                                                        admin_email: targetUser.email,
                                                        admin_password: resetPasswordSuccess.new_password,
                                                      }),
                                                    }
                                                  );
                                                  setCredentialEmailSent(res.ok ? "sent" : "failed");
                                                } catch {
                                                  setCredentialEmailSent("failed");
                                                } finally {
                                                  setCredentialEmailSending(false);
                                                }
                                              }}
                                            >
                                              {credentialEmailSending ? (
                                                <><Loader2 size={13} className="spin" /> Sending</>
                                              ) : credentialEmailSent === "sent" ? (
                                                <>✓ Sent</>
                                              ) : credentialEmailSent === "failed" ? (
                                                <><Mail size={13} /> Retry</>
                                              ) : (
                                                <><Mail size={13} /> Send via Email</>
                                              )}
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
                                  {editingUserId && (
                                    <div className="reset-password-panel">
                                      <div className="expand-section-head" style={{ marginBottom: 8 }}>
                                        <Pencil size={13} />
                                        <h4>
                                          Edit Member: {expandedUsers.find((u) => u._id === editingUserId)?.full_name}
                                        </h4>
                                      </div>
                                      <div className="flex-row gap-2 align-center" style={{ flexWrap: "wrap" }}>
                                        <input
                                          type="text"
                                          className="input-field input-sm"
                                          placeholder="Full Name"
                                          value={editUserForm.full_name}
                                          onChange={(e) => setEditUserForm((prev) => ({ ...prev, full_name: e.target.value }))}
                                          style={{ flex: "1 1 180px", minWidth: 150 }}
                                        />
                                        <input
                                          type="email"
                                          className="input-field input-sm"
                                          placeholder="Email"
                                          value={editUserForm.email}
                                          onChange={(e) => setEditUserForm((prev) => ({ ...prev, email: e.target.value }))}
                                          style={{ flex: "1 1 200px", minWidth: 180 }}
                                        />
                                        <select
                                          className="select-field input-sm"
                                          value={editUserForm.role}
                                          onChange={(e) => setEditUserForm((prev) => ({ ...prev, role: e.target.value }))}
                                          style={{ flex: "0 0 160px" }}
                                        >
                                          <option value="company_admin">Company Admin</option>
                                          <option value="sub_user">HR / Interviewer</option>
                                        </select>
                                        <button
                                          className="btn btn-primary btn-xs"
                                          onClick={() => handleSaveEditUser(editingUserId)}
                                          disabled={editUserLoading || !editUserForm.full_name || !editUserForm.email}
                                        >
                                          {editUserLoading ? "Saving…" : "Save Changes"}
                                        </button>
                                        <button
                                          className="btn btn-secondary btn-xs"
                                          onClick={() => setEditingUserId(null)}
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

        {activeTab === "leads" && (
          <LeadsPanel onConvertLead={handleConvertLead} onRefresh={refreshAllData} />
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
              Configure monthly price, user seat cap, and candidate limit for each plan tier.
            </p>
            <div className="plan-pricing-grid mt-4">
              {PLAN_TIERS.map((tier) => (
                <div key={tier.id} className="plan-pricing-row">
                  <div>
                    <strong>{tier.label}</strong>
                    <p className="text-xs text-muted">
                      {tier.max_credits.toLocaleString()} credits/mo (default allowance)
                    </p>
                  </div>
                  <div className="plan-pricing-fields">
                    <div className="plan-pricing-field">
                      <label className="text-xs text-muted">Max users</label>
                      <input
                        type="number"
                        className="input-field input-sm"
                        value={draftPlans[tier.id].max_users}
                        onChange={(e) => updateDraftPlan(tier.id, "max_users", e.target.value)}
                        min="1"
                        max="500"
                      />
                    </div>
                    <div className="plan-pricing-field">
                      <label className="text-xs text-muted">Max candidates</label>
                      <input
                        type="number"
                        className="input-field input-sm"
                        value={draftPlans[tier.id].max_candidates}
                        onChange={(e) => updateDraftPlan(tier.id, "max_candidates", e.target.value)}
                        min="1"
                        max="100000"
                      />
                    </div>
                    <div className="plan-pricing-field">
                      <label className="text-xs text-muted">Price ($/mo)</label>
                      <input
                        type="number"
                        className="input-field input-sm"
                        placeholder="Not set"
                        value={draftPlans[tier.id].price}
                        onChange={(e) => updateDraftPlan(tier.id, "price", e.target.value)}
                        min="0"
                        step="0.01"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <button className="btn btn-primary btn-sm mt-4" onClick={handleSavePricing} disabled={pricingSaving}>
              {pricingSaving ? "Saving…" : "Save Plan Settings"}
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
        onClose={handleOnboardingClose}
        onCompanyCreated={refreshAllData}
        leadId={onboardingLead?._id}
        initialData={onboardingLead ? {
          company_name: onboardingLead.company_name,
          industry: onboardingLead.industry || "Technology",
          contact_email: onboardingLead.work_email,
          contact_phone: onboardingLead.phone || "",
          contact_name: onboardingLead.contact_name,
          admin_name: onboardingLead.contact_name,
          admin_email: onboardingLead.work_email,
        } : null}
        onLeadConverted={refreshAllData}
      />
    </div>
  );
}
