import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
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
import { UsageView } from "./components/usage/UsageView";
import { LoadingScreen } from "./components/common/LoadingScreen";
import { InterviewApp } from "./components/interview/InterviewApp";
import { LandingPage } from "./components/marketing/LandingPage";
import { FeaturesPage } from "./components/marketing/FeaturesPage";
import { PricingPage } from "./components/marketing/PricingPage";
import { BookDemoPage } from "./components/marketing/BookDemoPage";
import { PrivacyPolicyPage } from "./components/marketing/PrivacyPolicyPage";
import { TermsPage } from "./components/marketing/TermsPage";
import { useAuth } from "./hooks/useAuth";
import { apiFetchJson } from "./utils/api";
import { ALLOWED_RESUME_EXTENSIONS } from "./constants";
import { useUploadProgress } from "./hooks/useUploadProgress";
import { UploadProgress } from "./components/resumes/UploadProgress";

/* ── BUG 33 fix: map URL segment ↔ view key ─────────────────────────────── */
const VALID_VIEWS = ["dashboard", "job", "resumes", "pipeline", "usage", "team"];

function viewFromPath(pathname) {
  // pathname expected: /app/pipeline  →  "pipeline"
  const seg = pathname.replace(/^\/app\/?/, "").split("/")[0];
  return VALID_VIEWS.includes(seg) ? seg : "dashboard";
}

function App() {
  const { user, role, hasPermission, refreshProfile, accessChanged, clearAccessChanged, permissions } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [workspace, setWorkspace] = useState(null);
  const [activeJobId, setActiveJobId] = useState(null);
  const [jobEditorMode, setJobEditorMode] = useState("edit");
  const [statusFilter, setStatusFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [previewCandidate, setPreviewCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const {
    activeBatch,
    isPolling: isUploadPolling,
    pollError,
    startTrackingBatch,
    clearBatch,
  } = useUploadProgress({
    onComplete: () => {
      refresh(activeJobId);
    },
  });

  // BUG 33: derive active view from the URL instead of local state
  const activeView = viewFromPath(location.pathname);

  // Revalidate permissions on navigation. This lives here rather than in
  // AuthProvider because the provider is mounted above <BrowserRouter> and so
  // cannot use useLocation. Debounced so a burst of navigation collapses into
  // one request, and skipped on the first render because the provider's
  // mount-time /api/auth/me already covers it.
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const timer = setTimeout(() => {
      refreshProfile();
    }, 300);
    return () => clearTimeout(timer);
  }, [location.pathname, refreshProfile]);

  const handleViewChange = (nextView) => {
    navigate(`/app/${nextView}`);
    setMenuOpen(false);
  };

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
      navigate("/app/dashboard");
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
    navigate("/app/job");
  }

  function openEditDrive(jobId) {
    setJobEditorMode("edit");
    switchDrive(jobId).then(() => navigate("/app/job"));
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
      navigate("/app/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    const invalid = Array.from(files).find(
      (f) => !ALLOWED_RESUME_EXTENSIONS.some((ext) => (f.name || "").toLowerCase().endsWith(ext))
    );
    if (invalid) {
      setError(`Unsupported file type for "${invalid.name}". Allowed formats: PDF, DOCX, TXT, PNG, JPG, JPEG.`);
      return;
    }
    setSaving(true);
    setError("");
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    try {
      const data = await apiFetchJson("/api/resumes/upload", {
        method: "POST",
        body: form,
      });
      if (data?.batchId) {
        startTrackingBatch(data.batchId);
      }
      if (data?.rejected && data.rejected.length > 0) {
        const rejectedSummary = data.rejected.map((r) => `${r.file_name}: ${r.error}`).join("\n");
        setError(`Some files were rejected:\n${rejectedSummary}`);
      }
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

  async function inviteCandidate(email, interviewType = "technical", override = null, deadline = "") {
    setSaving(true);
    setError("");
    try {
      const params = new URLSearchParams({
        interview_type: interviewType,
        send_email: "true",
      });
      if (override?.reason) params.set("override_reason", override.reason);
      if (override?.note) params.set("override_note", override.note);
      const effectiveDeadline = deadline || override?.deadline;
      if (effectiveDeadline) params.set("deadline", effectiveDeadline);
      const data = await apiFetchJson(
        `/api/candidates/${encodeURIComponent(email)}/invite?${params.toString()}`,
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
        onViewChange={handleViewChange}
        company={workspace?.company}
        drives={drives}
        activeJobId={activeJobId}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />
      <main className="main-panel">
        <Topbar
          title={titleFor(effectiveView)}
          company={workspace?.company}
          onMenuClick={() => setMenuOpen(true)}
        />

        {error ? <div className="notice error">{error}</div> : null}

        {accessChanged ? (
          <div className="notice info access-changed-notice">
            <span>Your access was updated by an administrator. Menu items you no longer have permission for have been removed.</span>
            <button type="button" className="text-button" onClick={clearAccessChanged}>
              Dismiss
            </button>
          </div>
        ) : null}

        {/* Zero permissions: viewAllowed would silently bounce every nav here,
            which reads as breakage rather than an access change. */}
        {isCompanyAdmin || permissions.length > 0 ? null : (
          <div className="notice error">
            Your account has no permissions assigned. Contact your company administrator to restore access.
          </div>
        )}

        {effectiveView === "dashboard" && (
          <>
            {activeBatch ? (
              <UploadProgress batch={activeBatch} onDismiss={clearBatch} pollError={pollError} />
            ) : null}
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
              onGoToUpload={canManageResumes ? () => navigate("/app/resumes") : undefined}
              {...driveProps}
            />
          </>
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
          <ResumeIntake
            onManualResume={addManualResume}
            onUpload={uploadFiles}
            saving={saving || isUploadPolling}
            uploadBatch={activeBatch}
            onDismissBatch={clearBatch}
            pollError={pollError}
          />
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
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
      <Route path="/*" element={<App />} />
    </Routes>
  );
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
      <Route path="/privacy" element={<PrivacyPolicyPage />} />
      <Route path="/terms" element={<TermsPage />} />
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
