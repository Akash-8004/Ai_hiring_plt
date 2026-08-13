import React, { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Field } from "../common/Field";

function splitCsv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function JobEditor({ job, onSave, saving }) {
  const [form, setForm] = useState({
    ...job,
    required_skills: job.required_skills.join(", "),
    nice_to_have_skills: job.nice_to_have_skills.join(", "),
  });

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave({
      ...form,
      experience_years: Number(form.experience_years),
      threshold: Number(form.threshold),
      required_skills: splitCsv(form.required_skills),
      nice_to_have_skills: splitCsv(form.nice_to_have_skills),
    });
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <section className="form-panel wide">
        <h2>Job Profile</h2>
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
        <label className="field full">
          <span>Shortlist threshold: {form.threshold}%</span>
          <input type="range" min="40" max="100" value={form.threshold} onChange={(event) => update("threshold", event.target.value)} />
        </label>
        <button className="primary-button submit-button" disabled={saving}>
          {saving ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
          Save JD
        </button>
      </section>
    </form>
  );
}
