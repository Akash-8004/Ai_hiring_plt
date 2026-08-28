import React, { useState } from "react";
import { Loader2, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import { Field } from "../common/Field";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function splitCsv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function blankQuestion() {
  return { question: "", topic: "General", difficulty: "medium", expected_points: [] };
}

function blankJobForm() {
  return {
    title: "",
    department: "",
    location: "",
    experience_years: 0,
    required_skills: "",
    nice_to_have_skills: "",
    education: "",
    description: "",
    threshold: 80,
    hr_interview_duration: 7,
    technical_interview_duration: 5,
  };
}

export function JobEditor({ job, jobId, mode = "edit", driveCount = 0, maxJobs = 3, onSave, saving }) {
  const source = mode === "create" || !job ? blankJobForm() : job;
  const [form, setForm] = useState({
    ...source,
    required_skills: Array.isArray(source.required_skills) ? source.required_skills.join(", ") : source.required_skills || "",
    nice_to_have_skills: Array.isArray(source.nice_to_have_skills) ? source.nice_to_have_skills.join(", ") : source.nice_to_have_skills || "",
  });
  const [questions, setQuestions] = useState(mode === "create" ? [] : (job?.custom_questions || []));
  const [manualText, setManualText] = useState("");
  const [processing, setProcessing] = useState(false);
  const [processingError, setProcessingError] = useState("");

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave({
      ...form,
      experience_years: Number(form.experience_years),
      threshold: Number(form.threshold),
      hr_interview_duration: Number(form.hr_interview_duration) || 7,
      technical_interview_duration: Number(form.technical_interview_duration) || 5,
      required_skills: splitCsv(form.required_skills),
      nice_to_have_skills: splitCsv(form.nice_to_have_skills),
      custom_questions: questions
        .map((q) => ({ ...q, question: q.question.trim() }))
        .filter((q) => q.question),
    });
  }

  async function processManualText() {
    if (!manualText.trim()) return;
    setProcessing(true);
    setProcessingError("");
    try {
      const response = await fetch(`${API_BASE}/api/job/questions/process-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: manualText }),
      });
      if (!response.ok) throw new Error("Could not process questions");
      const data = await response.json();
      if (data.message) setProcessingError(data.message);
      setQuestions(data.questions);
      setManualText("");
    } catch (err) {
      setProcessingError(err.message);
    } finally {
      setProcessing(false);
    }
  }

  async function processFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setProcessing(true);
    setProcessingError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch(`${API_BASE}/api/job/questions/process`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Could not process questions file");
      const data = await response.json();
      if (data.message) setProcessingError(data.message);
      setQuestions(data.questions);
    } catch (err) {
      setProcessingError(err.message);
    } finally {
      setProcessing(false);
      event.target.value = "";
    }
  }

  function updateQuestion(index, field, value) {
    setQuestions((current) =>
      current.map((question, i) => (i === index ? { ...question, [field]: value } : question))
    );
  }

  function removeQuestion(index) {
    setQuestions((current) => current.filter((_, i) => i !== index));
  }

  function addQuestion() {
    setQuestions((current) => [...current, blankQuestion()]);
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <section className="form-panel wide">
        <h2>{mode === "create" ? "Create Job Drive" : "Edit Job Drive"}</h2>
        <p className="text-sm text-muted mb-3">
          {driveCount} of {maxJobs} drives used
        </p>
        <div className="field-grid">
          <Field label="Job title" value={form.title} onChange={(value) => update("title", value)} />
          <Field label="Department" value={form.department} onChange={(value) => update("department", value)} />
          <Field label="Location" value={form.location} onChange={(value) => update("location", value)} />
          <Field label="Minimum experience" type="number" value={form.experience_years} onChange={(value) => update("experience_years", value)} />
        </div>
        <label className="field full">
          <span>JD / responsibilities</span>
          <textarea value={form.description} onChange={(event) => update("description", event.target.value)} rows={8} />
        </label>
      </section>

      <section className="form-panel">
        <h2>AI Screening</h2>
        <label className="field full">
          <span>Required skills</span>
          <textarea value={form.required_skills} onChange={(event) => update("required_skills", event.target.value)} rows={4} />
        </label>
        <label className="field full">
          <span>Nice to have</span>
          <textarea value={form.nice_to_have_skills} onChange={(event) => update("nice_to_have_skills", event.target.value)} rows={4} />
        </label>
        <Field label="Education" value={form.education} onChange={(value) => update("education", value)} />
        <label className="field">
          <span>HR Round Duration (minutes)</span>
          <input type="number" min="3" max="60" value={form.hr_interview_duration || 7} onChange={(event) => update("hr_interview_duration", event.target.value)} />
        </label>
        <label className="field">
          <span>Technical Round Duration (minutes)</span>
          <input type="number" min="3" max="60" value={form.technical_interview_duration || 5} onChange={(event) => update("technical_interview_duration", event.target.value)} />
        </label>
        <label className="field full">
          <span>Shortlist threshold: {form.threshold}%</span>
          <input type="range" min="40" max="100" value={form.threshold} onChange={(event) => update("threshold", event.target.value)} />
        </label>
        <button className="primary-button submit-button" disabled={saving}>
          {saving ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
          {mode === "create" ? "Create Drive" : "Save JD"}
        </button>
      </section>

      <section className="form-panel full">
        <h2>Custom Technical Questions <span className="optional-tag">optional</span></h2>
        <p className="panel-hint">
          Upload a question bank (PDF, DOCX, or TXT) or paste raw technical / coding questions.
          The AI will restructure them into a clean format and they will be asked to candidates
          during the technical interview, with a textbox to type the answer.
        </p>

        <label className="field full">
          <span>Paste questions (one per line)</span>
          <textarea
            value={manualText}
            onChange={(event) => setManualText(event.target.value)}
            rows={5}
            placeholder={"1. Write a function to reverse a linked list\n2. Explain the difference between SQL and NoSQL"}
          />
        </label>

        <div className="questions-actions">
          <button type="button" className="secondary-button" onClick={processManualText} disabled={processing || !manualText.trim()}>
            {processing ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            Restructure with AI
          </button>
          <label className="secondary-button file-button">
            <Upload size={16} />
            Upload file
            <input type="file" accept=".pdf,.docx,.txt" onChange={processFile} hidden />
          </label>
        </div>

        {processingError ? <div className="notice info">{processingError}</div> : null}

        {questions.length ? (
          <div className="questions-list">
            <div className="questions-list-head">
              <h3>Structured questions ({questions.length})</h3>
              <button type="button" className="secondary-button small" onClick={addQuestion}>
                <Plus size={15} /> Add
              </button>
            </div>
            {questions.map((question, index) => (
              <div key={index} className="question-item">
                <textarea
                  rows={3}
                  value={question.question}
                  onChange={(event) => updateQuestion(index, "question", event.target.value)}
                  placeholder="Question text"
                />
                <div className="question-meta">
                  <input
                    value={question.topic || "General"}
                    onChange={(event) => updateQuestion(index, "topic", event.target.value)}
                    placeholder="Topic"
                  />
                  <select value={question.difficulty || "medium"} onChange={(event) => updateQuestion(index, "difficulty", event.target.value)}>
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                  <button type="button" className="icon-button danger" onClick={() => removeQuestion(index)} title="Remove question">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </form>
  );
}
