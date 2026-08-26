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
import { LoadingScreen } from "./components/common/LoadingScreen";
import { InterviewApp } from "./components/interview/InterviewApp";
import { useAuth } from "./hooks/useAuth";
import { apiFetchJson } from "./utils/api";

function App() {
  const { user, role, hasPermission } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [activeView, setActiveView] = useState("dashboard");
  const [statusFilter, setStatusFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setError("");
    try {
      const data = await apiFetchJson("/api/workspace");
      setWorkspace(data);
    } catch (err) {
      setError(err.message || "Failed to load workspace data");
    }
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false));
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
      const data = await apiFetchJson("/api/job", {
        method: "PUT",
        body: JSON.stringify(job),
      });
      setWorkspace(data);
      setActiveView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
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
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingScreen />;
  }

  // Granular access flags (backend enforces these too; this keeps the UI honest).
  const isCompanyAdmin = role === "company_admin" || role === "super_admin";
  const canManageResumes = hasPermission("manage_resumes");
  const canViewPipeline = hasPermission("view_pipeline");
  const canConductInterviews = hasPermission("conduct_interviews");

  // If the active view is one the user isn't allowed to see, fall back to the
  // dashboard so a restricted member can never land on a forbidden screen.
  const viewAllowed = (view) => {
    if (view === "resumes") return canManageResumes;
    if (view === "pipeline") return canViewPipeline;
    if (view === "job" || view === "team") return isCompanyAdmin;
    return true;
  };
  const effectiveView = viewAllowed(activeView) ? activeView : "dashboard";

  return (
    <div className="app-shell">
      <Sidebar activeView={effectiveView} onViewChange={setActiveView} company={workspace?.company} />
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
            onGoToJob={isCompanyAdmin ? () => setActiveView("job") : undefined}
            onGoToUpload={canManageResumes ? () => setActiveView("resumes") : undefined}
          />
        )}

        {effectiveView === "job" && (
          <JobEditor job={workspace?.job} onSave={saveJob} saving={saving} />
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
    job: "Job Setup",
    resumes: "Resume Intake",
    pipeline: "Hiring Pipeline",
    team: "Team Access Management",
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

  // Public candidate interview sessions don't require workspace login
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
