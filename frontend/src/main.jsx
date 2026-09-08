import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import "./styles.css";

import { AuthProvider } from "./components/auth/AuthProvider";
import { LoginPage } from "./components/auth/LoginPage";
import { SuperAdminDashboard } from "./components/admin/SuperAdminDashboard";
import { TeamManagementView } from "./components/team/TeamManagementView";
import { Sidebar } from "./components/layout/Sidebar";
import { Topbar } from "./components/layout/Topbar";
import { Dashboard, matchesCandidateFilter } from "./components/dashboard/Dashboard";
import { JobEditor } from "./components/job/JobEditor";
import { JdApprovalPanel } from "./components/job/JdApprovalPanel";
import { ResumeIntake } from "./components/resumes/ResumeIntake";
import { Pipeline } from "./components/pipeline/Pipeline";
import { CandidatePanel } from "./components/candidate/CandidatePanel";
import { CandidateResumePreview } from "./components/candidate/CandidateResumePreview";
import { SettingsView } from "./components/settings/SettingsView";
import { UsageView } from "./components/usage/UsageView";
import { LoadingScreen } from "./components/common/LoadingScreen";
import { InterviewApp } from "./components/interview/InterviewApp";
import { LandingPage } from "./components/marketing/LandingPage";
import { FeaturesPage } from "./components/marketing/FeaturesPage";
import { PricingPage } from "./components/marketing/PricingPage";
import { BookDemoPage } from "./components/marketing/BookDemoPage";
import { useAuth } from "./hooks/useAuth";
import { apiFetchJson } from "./utils/api";

function App() {
  const { user, role, hasPermission } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeView, setActiveView] = useState("dashboard");
  const [jobEditorMode, setJobEditorMode] = useState("edit");
  const [statusFilter, setStatusFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [previewCandidate, setPreviewCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh(jobId = activeJobId) {
    setError("");
    try {
      const qs = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
      const data = await apiFetchJson(`/api/workspace${qs}`);
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
    } catch (err) {
      setError(err.message || "Failed to load workspace data");
    }
  }

  useEffect(() => {
    refresh(null).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const candidates = useMemo(() => {
    const items = workspace?.candidates || [];
    return items.filter((candidate) => {
      const matchesStatus = matchesCandidateFilter(candidate, statusFilter);
      const searchable = `${candidate.Name} ${candidate.Email} ${candidate.Phone || ""} ${candidate.Skills}`.toLowerCase();
      return matchesStatus && searchable.includes(query.toLowerCase());
    });
  }, [workspace, statusFilter, query]);

  async function saveJob(job) {
    setSaving(true);
    setError("");
    try {
      const body = { ...job, job_id: jobEditorMode === "create" ? null : activeJobId };
      const data = await apiFetchJson("/api/job", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
      if (data.jd_request) {
        alert(
          `Your ${jobEditorMode === "create" ? "new drive request" : "changes"} have been submitted for company admin approval.`
        );
      }
      setJobEditorMode("edit");
      setActiveView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function switchDrive(jobId) {
    setSaving(true);
    setError("");
    try {
      await refresh(jobId);
    } finally {
      setSaving(false);
    }
  }

  async function deleteDrive(drive) {
    const count = drive.candidate_count ?? 0;
    const msg = isCompanyAdmin
      ? `Delete drive "${drive.title}"? This permanently removes the drive and all ${count} of its candidates.`
      : `Submit deletion request for drive "${drive.title}"? As a team member, this will be submitted to a Company Admin for approval before the drive is deleted.`;
    if (!window.confirm(msg)) return;
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson(`/api/job/${encodeURIComponent(drive.job_id)}`, { method: "DELETE" });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
      if (data.jd_request) {
        alert(`Your request to delete drive "${drive.title}" has been submitted for company admin approval.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function openCreateDrive() {
    setJobEditorMode("create");
    setActiveView("job");
  }

  function openEditDrive(jobId) {
    setJobEditorMode("edit");
    switchDrive(jobId).then(() => setActiveView("job"));
  }

  async function addManualResume(payload) {
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson("/api/resumes/manual", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
      setActiveView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    setSaving(true);
    setError("");
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    try {
      const data = await apiFetchJson("/api/resumes/upload", {
        method: "POST",
        body: form,
      });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
      setActiveView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function postAction(path, method = "POST") {
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson(path, { method });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function inviteCandidate(email, interviewType = "technical") {
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson(
        `/api/candidates/${encodeURIComponent(email)}/invite?interview_type=${interviewType}&send_email=true`,
        { method: "POST" }
      );
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function updateDeadline(interviewType, deadline) {
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson(`/api/job/deadline?interview_type=${interviewType}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deadline: deadline || null }),
      });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingScreen />;
  }

  const isCompanyAdmin = role === "company_admin" || role === "super_admin";
  const canManageResumes = hasPermission("manage_resumes");
  const canViewPipeline = hasPermission("view_pipeline");
  const canConductInterviews = hasPermission("conduct_interviews");
  const canManageJobs = isCompanyAdmin || hasPermission("manage_jobs");
  const canDeleteDrive = isCompanyAdmin || hasPermission("manage_drive_delete") || hasPermission("manage_jobs");
  const drives = workspace?.drives || [];
  const jdRequests = workspace?.jd_requests || [];
  const pendingRequest = jdRequests.find(
    (r) =>
      r.status === "pending" &&
      (r.job_id === activeJobId ||
        (!isCompanyAdmin && jobEditorMode === "create" && r.target_status === "create"))
  );

  async function refreshAfterJdAction() {
    await refresh(activeJobId);
  }

  const viewAllowed = (view) => {
    if (view === "resumes") return canManageResumes;
    if (view === "pipeline") return canViewPipeline;
    if (view === "job") return canManageJobs;
    if (view === "team") return isCompanyAdmin;
    if (view === "usage") return isCompanyAdmin || hasPermission("view_usage");
    return true;
  };
  const effectiveView = viewAllowed(activeView) ? activeView : "dashboard";

  const driveProps = {
    drives,
    activeJobId,
    onSwitchDrive: switchDrive,
    onEditDrive: openEditDrive,
    onDeleteDrive: deleteDrive,
    onCreateDrive: openCreateDrive,
    canCreateDrive: canManageJobs,
    canDeleteDrive,
  };

  return (
    <div className="app-shell">
      <Sidebar
        activeView={effectiveView}
        onViewChange={setActiveView}
        company={workspace?.company}
        drives={drives}
        activeJobId={activeJobId}
      />
      <main className="main-panel">
        <Topbar
          title={titleFor(effectiveView)}
          company={workspace?.company}
        />

        {error ? <div className="notice error">{error}</div> : null}

        {effectiveView === "dashboard" && (
          <Dashboard
            workspace={workspace}
            candidates={candidates}
            statusFilter={statusFilter}
            query={query}
            onStatusFilter={setStatusFilter}
            onQuery={setQuery}
            onCandidate={setSelectedCandidate}
            onViewDetails={setPreviewCandidate}
            onGoToJob={canManageJobs ? (activeJobId ? () => openEditDrive(activeJobId) : openCreateDrive) : undefined}
            onGoToUpload={canManageResumes ? () => setActiveView("resumes") : undefined}
            {...driveProps}
          />
        )}

        {effectiveView === "job" && (
          <>
            <JdApprovalPanel
              requests={jdRequests}
              onResolved={refreshAfterJdAction}
              isCompanyAdmin={isCompanyAdmin}
            />
            <JobEditor
              job={jobEditorMode === "create" ? null : workspace?.job}
              jobId={jobEditorMode === "create" ? null : activeJobId}
              mode={jobEditorMode}
              onSave={saveJob}
              saving={saving}
              pendingRequest={pendingRequest}
              isCompanyAdmin={isCompanyAdmin}
            />
          </>
        )}

        {effectiveView === "resumes" && (
          <ResumeIntake onManualResume={addManualResume} onUpload={uploadFiles} saving={saving} />
        )}

        {effectiveView === "pipeline" && (
          <Pipeline
            candidates={workspace?.candidates || []}
            onInvite={inviteCandidate}
            onRefresh={refresh}
            onDeadline={updateDeadline}
            deadlines={workspace?.deadlines}
            canInvite={canConductInterviews}
            busy={saving}
          />
        )}

        {effectiveView === "team" && <TeamManagementView />}

        {effectiveView === "usage" && <UsageView />}

        {effectiveView === "settings" && <SettingsView />}
      </main>

      {selectedCandidate ? (
        <CandidatePanel candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
      ) : null}
      {previewCandidate ? (
        <CandidateResumePreview candidate={previewCandidate} onClose={() => setPreviewCandidate(null)} />
      ) : null}
    </div>
  );
}

function titleFor(view) {
  return {
    dashboard: "Hiring Dashboard",
    job: "Job Drives",
    resumes: "Resume Intake",
    pipeline: "Hiring Pipeline",
    team: "Team Access Management",
    usage: "Usage & Credits",
    settings: "Workspace Settings",
  }[view] || "Workspace";
}

function LoginRoute() {
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate("/app", { replace: true });
    }
  }, [isAuthenticated, loading, navigate]);

  if (loading) return <LoadingScreen />;
  if (isAuthenticated) return null;
  return <LoginPage />;
}

function ProtectedApp() {
  const { isAuthenticated, loading, role } = useAuth();

  if (loading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (role === "super_admin") return <SuperAdminDashboard />;
  return <App />;
}

function InterviewGate({ children }) {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("interview");
  if (token) {
    return <InterviewApp token={token} interviewType={params.get("type") || "technical"} />;
  }
  return children;
}

function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/features" element={<FeaturesPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/book-a-demo" element={<BookDemoPage />} />
      <Route path="/contact" element={<Navigate to="/book-a-demo" replace />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/app/*" element={<ProtectedApp />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")).render(
  <InterviewGate>
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </BrowserRouter>
  </InterviewGate>
);
