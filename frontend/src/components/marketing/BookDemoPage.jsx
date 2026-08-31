import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  CheckCircle2, ArrowLeft, ArrowRight, Sparkles, ShieldCheck,
  Calendar, Clock, Users, Star,
} from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import { apiFetchJson } from "../../utils/api";
import "./marketing.css";

const TEAM_SIZES = ["1-10 employees", "11-50 employees", "51-200 employees", "201-500 employees", "500+ employees"];
const HIRING_VOLUMES = ["1-5 roles / month", "6-15 roles / month", "16-50 roles / month", "50+ roles / month"];

export function BookDemoPage() {
  const [searchParams] = useSearchParams();
  const planParam = searchParams.get("plan");
  const solutionParam = searchParams.get("solution");

  const [form, setForm] = useState({
    company_name: "",
    industry: "",
    contact_name: "",
    work_email: "",
    phone: "",
    team_size: "",
    hiring_volume: "",
    message: planParam
      ? `Interested in the ${planParam.toUpperCase()} plan.`
      : solutionParam
      ? `Looking for solutions tailored for ${solutionParam.toUpperCase()}.`
      : "",
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetchJson("/api/public/leads", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Failed to submit request. Please verify your details.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <MarketingLayout>
        <div className="mkt-form-success">
          <CheckCircle2 size={64} color="#10b981" />
          <h2>Thank you! We&apos;ll be in touch shortly.</h2>
          <p>
            Our hiring technology specialists have received your details and will reach out to schedule your personalized live demo.
          </p>
          <div style={{ marginTop: "2.5rem" }}>
            <Link to="/" className="mkt-btn mkt-btn-secondary mkt-btn-lg">
              <ArrowLeft size={16} /> Return to Homepage
            </Link>
          </div>
        </div>
      </MarketingLayout>
    );
  }

  return (
    <MarketingLayout>
      <div className="mkt-split-page">
        {/* ── Left Column: Value Prop & Trust ───────────────────────────── */}
        <div className="mkt-split-info">
          <span className="mkt-eyebrow">
            <Sparkles size={13} /> Tailored Walkthrough
          </span>
          <h1>Experience the future of hiring in real time</h1>
          <p className="lead">
            Book a 30-minute interactive session with our product experts to see how HireAI can eliminate screening bottlenecks for your team.
          </p>

          <div className="mkt-value-list">
            <div className="mkt-value-item">
              <div className="mkt-value-icon">
                <Calendar size={20} />
              </div>
              <div className="mkt-value-text">
                <h4>Customized Platform Demonstration</h4>
                <p>See live voice AI interviewing tailored to your engineering stack and hiring standards.</p>
              </div>
            </div>

            <div className="mkt-value-item">
              <div className="mkt-value-icon">
                <Clock size={20} />
              </div>
              <div className="mkt-value-text">
                <h4>ROI &amp; Time-Savings Calculation</h4>
                <p>Discover how much recruiter and engineering bandwidth HireAI saves each week.</p>
              </div>
            </div>

            <div className="mkt-value-item">
              <div className="mkt-value-icon">
                <ShieldCheck size={20} />
              </div>
              <div className="mkt-value-text">
                <h4>Enterprise Security &amp; RBAC Briefing</h4>
                <p>Learn about multi-tenant isolation, proctoring compliance, and audit logging.</p>
              </div>
            </div>
          </div>

          <div style={{ padding: "1.5rem", background: "var(--mkt-card)", border: "1px solid var(--mkt-border)", borderRadius: "14px" }}>
            <div style={{ display: "flex", gap: "3px", color: "#f59e0b", marginBottom: "0.6rem" }}>
              {[...Array(5)].map((_, i) => (
                <Star key={i} size={15} fill="#f59e0b" color="#f59e0b" />
              ))}
            </div>
            <p style={{ color: "#cbd5e1", fontSize: "0.9rem", fontStyle: "italic", margin: "0 0 0.75rem" }}>
              &ldquo;The demo showed us exactly how HireAI would cut our technical phone screen load from 12 hours a week to zero.&rdquo;
            </p>
            <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "#ffffff" }}>
              Director of Engineering &middot; High-growth SaaS
            </div>
          </div>
        </div>

        {/* ── Right Column: Lead Form ───────────────────────────────────── */}
        <div className="mkt-form-card">
          <h2>Request a live demo</h2>
          <p className="form-sub">Fill in your information and we will get back to you within 24 hours.</p>

          {error && <div className="mkt-form-error">{error}</div>}

          <form className="mkt-form" onSubmit={handleSubmit}>
            <div className="mkt-form-row">
              <div className="mkt-form-group">
                <label>Company Name *</label>
                <input
                  value={form.company_name}
                  onChange={update("company_name")}
                  placeholder="e.g. Acme Corp"
                  required
                />
              </div>
              <div className="mkt-form-group">
                <label>Industry</label>
                <input
                  value={form.industry}
                  onChange={update("industry")}
                  placeholder="e.g. Fintech, Healthcare"
                />
              </div>
            </div>

            <div className="mkt-form-row">
              <div className="mkt-form-group">
                <label>Your Full Name *</label>
                <input
                  value={form.contact_name}
                  onChange={update("contact_name")}
                  placeholder="e.g. Sarah Jenkins"
                  required
                />
              </div>
              <div className="mkt-form-group">
                <label>Work Email *</label>
                <input
                  type="email"
                  value={form.work_email}
                  onChange={update("work_email")}
                  placeholder="sarah@company.com"
                  required
                />
              </div>
            </div>

            <div className="mkt-form-row">
              <div className="mkt-form-group">
                <label>Phone Number</label>
                <input
                  type="tel"
                  value={form.phone}
                  onChange={update("phone")}
                  placeholder="+1 (555) 000-0000"
                />
              </div>
              <div className="mkt-form-group">
                <label>Team Size</label>
                <select value={form.team_size} onChange={update("team_size")}>
                  <option value="">Select team size...</option>
                  {TEAM_SIZES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mkt-form-group">
              <label>Estimated Monthly Hiring Volume</label>
              <select value={form.hiring_volume} onChange={update("hiring_volume")}>
                <option value="">Select hiring volume...</option>
                {HIRING_VOLUMES.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>

            <div className="mkt-form-group">
              <label>Message / Specific Hiring Goals</label>
              <textarea
                value={form.message}
                onChange={update("message")}
                placeholder="Tell us about your hiring challenges or specific requirements..."
              />
            </div>

            <button
              type="submit"
              className="mkt-btn mkt-btn-primary mkt-btn-lg"
              disabled={loading}
              style={{ marginTop: "0.5rem" }}
            >
              {loading ? "Scheduling Demo..." : "Schedule My Demo"} <ArrowRight size={17} />
            </button>
          </form>
        </div>
      </div>
    </MarketingLayout>
  );
}
