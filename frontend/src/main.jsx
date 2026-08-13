import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

import { Sidebar } from "./components/layout/Sidebar";
import { Topbar } from "./components/layout/Topbar";
import { Dashboard } from "./components/dashboard/Dashboard";
import { JobEditor } from "./components/job/JobEditor";
import { ResumeIntake } from "./components/resumes/ResumeIntake";
import { Pipeline } from "./components/pipeline/Pipeline";
import { CandidatePanel } from "./components/candidate/CandidatePanel";
import { SettingsView } from "./components/settings/SettingsView";
import { LoadingScreen } from "./components/common/LoadingScreen";
import { InterviewApp } from "./components/interview/InterviewApp";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function App() {
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
    const response = await fetch(`${API_BASE}/api/workspace`);
    if (!response.ok) {
      throw new Error("API is not responding");
    }
    setWorkspace(await response.json());
  }

  useEffect(() => {
    refresh()
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const candidates = useMemo(() => {
    const items = workspace?.candidates || [];
    return items.filter((candidate) => {
      const matchesStatus = statusFilter === "All" || candidate.Status === statusFilter;
      const searchable = `${candidate.Name} ${candidate.Email} ${candidate.Skills}`.toLowerCase();
      return matchesStatus && searchable.includes(query.toLowerCase());
    });
  }, [workspace, statusFilter, query]);

  async function saveJob(job) {
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/job`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(job),
      });
      if (!response.ok) throw new Error("Could not save JD");
      setWorkspace(await response.json());
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
      const response = await fetch(`${API_BASE}/api/resumes/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Could not add resume");
      setWorkspace(await response.json());
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
      const response = await fetch(`${API_BASE}/api/resumes/upload`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error("Could not upload resumes");
      setWorkspace(await response.json());
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
      const response = await fetch(`${API_BASE}${path}`, { method });
      if (!response.ok) throw new Error("Request failed");
      setWorkspace(await response.json());
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
      const response = await fetch(
        `${API_BASE}/api/candidates/${encodeURIComponent(email)}/invite?interview_type=${interviewType}`,
        { method: "POST" }
      );
      if (!response.ok) throw new Error("Could not create invitation");
      setWorkspace(await response.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingScreen />;
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onViewChange={setActiveView} company={workspace?.company} />
      <main className="main-panel">
        <Topbar
          title={titleFor(activeView)}
          company={workspace?.company}
          busy={saving}
          onLoadSamples={() => postAction("/api/resumes/sample")}
          onClear={() => postAction("/api/resumes", "DELETE")}
        />

        {error ? <div className="notice error">{error}</div> : null}

        {activeView === "dashboard" && (
          <Dashboard
            workspace={workspace}
            candidates={candidates}
            statusFilter={statusFilter}
            query={query}
            onStatusFilter={setStatusFilter}
            onQuery={setQuery}
            onCandidate={setSelectedCandidate}
            onGoToJob={() => setActiveView("job")}
            onGoToUpload={() => setActiveView("resumes")}
          />
        )}

        {activeView === "job" && (
          <JobEditor job={workspace.job} onSave={saveJob} saving={saving} />
        )}

        {activeView === "resumes" && (
          <ResumeIntake onManualResume={addManualResume} onUpload={uploadFiles} saving={saving} />
        )}

        {activeView === "pipeline" && (
          <Pipeline
            candidates={workspace.candidates}
            onInvite={inviteCandidate}
            busy={saving}
          />
        )}
        {activeView === "settings" && <SettingsView />}
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
    settings: "Workspace Settings",
  }[view];
}

function Root() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("interview");
  const interviewType = params.get("type") || "technical";
  if (token) {
    return <InterviewApp token={token} interviewType={interviewType} />;
  }
  return <App />;
}

createRoot(document.getElementById("root")).render(<Root />);
