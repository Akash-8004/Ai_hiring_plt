import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

import { AuthProvider } from "./components/auth/AuthProvider";
import { LoginPage } from "./components/auth/LoginPage";
import { SuperAdminDashboard } from "./components/admin/SuperAdminDashboard";
import { TeamManagementView } from "./components/team/TeamManagementView";
import { Sidebar } from "./components/layout/Sidebar";
import { Topbar } from "./components/layout/Topbar";
import { Dashboard, matchesCandidateFilter } from "./components/dashboard/Dashboard";
import { JobEditor } from "./components/job/JobEditor";
import { ResumeIntake } from "./components/resumes/ResumeIntake";
import { Pipeline } from "./components/pipeline/Pipeline";
import { CandidatePanel } from "./components/candidate/CandidatePanel";
import { SettingsView } from "./components/settings/SettingsView";
import { UsageView } from "./components/usage/UsageView";
import { LoadingScreen } from "./components/common/LoadingScreen";
import { InterviewApp } from "./components/interview/InterviewApp";
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
    const msg = `Delete drive "${drive.title}"? This permanently removes the drive and all ${count} of its candidates.`;
    if (!window.confirm(msg)) return;
    setSaving(true);
    setError("");
    try {
      const data = await apiFetchJson(`/api/job/${encodeURIComponent(drive.job_id)}`, { method: "DELETE" });
      setWorkspace(data);
      setActiveJobId(data.job_id || null);
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
        `/api/candidates/${encodeURIComponent(email)}/invite?interview_type=${interviewType}`,
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

  if (loading) {
    return <LoadingScreen />;
  }

  const isCompanyAdmin = role === "company_admin" || role === "super_admin";
  const canManageResumes = hasPermission("manage_resumes");
  const canViewPipeline = hasPermission("view_pipeline");
  const canConductInterviews = hasPermission("conduct_interviews");
  const canManageJobs = isCompanyAdmin || hasPermission("manage_jobs");
  const canDeleteDrive = isCompanyAdmin || hasPermission("manage_drive_delete");
  const maxJobs = workspace?.company?.max_jobs ?? 3;
  const drives = workspace?.drives || [];

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
    maxJobs,
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
          busy={saving}
          onLoadSamples={() => postAction("/api/resumes/sample")}
          onClear={() => postAction("/api/resumes", "DELETE")}
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
            onGoToJob={canManageJobs ? openCreateDrive : undefined}
            onGoToUpload={canManageResumes ? () => setActiveView("resumes") : undefined}
            {...driveProps}
          />
        )}

        {effectiveView === "job" && (
          <JobEditor
            job={jobEditorMode === "create" ? null : workspace?.job}
            jobId={jobEditorMode === "create" ? null : activeJobId}
            mode={jobEditorMode}
            driveCount={drives.length}
            maxJobs={maxJobs}
            onSave={saveJob}
            saving={saving}
          />
        )}

        {effectiveView === "resumes" && (
          <ResumeIntake onManualResume={addManualResume} onUpload={uploadFiles} saving={saving} />
        )}

        {effectiveView === "pipeline" && (
          <Pipeline
            candidates={workspace?.candidates || []}
            onInvite={inviteCandidate}
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

function AuthRouter() {
  const { isAuthenticated, loading, role } = useAuth();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  if (role === "super_admin") {
    return <SuperAdminDashboard />;
  }

  return <App />;
}

function Root() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("interview");
  const interviewType = params.get("type") || "technical";

  if (token) {
    return <InterviewApp token={token} interviewType={interviewType} />;
  }

  return (
    <AuthProvider>
      <AuthRouter />
    </AuthProvider>
  );
}

createRoot(document.getElementById("root")).render(<Root />);
