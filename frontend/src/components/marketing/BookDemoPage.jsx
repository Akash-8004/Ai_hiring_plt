import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  CheckCircle2, ArrowLeft, ArrowRight, RefreshCw, Sparkles, ShieldCheck,
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

  const [captcha, setCaptcha] = useState({ token: "", question: "" });
  const [captchaAnswer, setCaptchaAnswer] = useState("");
  // "loading" | "ready" | "error" — kept separate from `captcha.question` so a
  // failed fetch is never rendered as an indefinite "Loading..." state.
  const [captchaStatus, setCaptchaStatus] = useState("loading");
  const [captchaError, setCaptchaError] = useState("");

  // Monotonic request id: only the newest challenge may write state, so a slow
  // earlier response cannot overwrite a newer token/question pair.
  const captchaReqRef = useRef(0);
  const captchaAbortRef = useRef(null);

  const loadCaptcha = useCallback(async () => {
    const reqId = captchaReqRef.current + 1;
    captchaReqRef.current = reqId;

    captchaAbortRef.current?.abort();
    const controller = new AbortController();
    captchaAbortRef.current = controller;

    setCaptchaStatus("loading");
    setCaptchaError("");

    try {
      const data = await apiFetchJson("/api/public/captcha", {
        signal: controller.signal,
        timeout: 10000,
      });
      if (reqId !== captchaReqRef.current) return;
      setCaptcha({ token: data.token, question: data.question });
      setCaptchaAnswer("");
      setCaptchaStatus("ready");
    } catch (err) {
      if (reqId !== captchaReqRef.current) return;
      if (err?.name === "AbortError") return;
      setCaptcha({ token: "", question: "" });
      setCaptchaAnswer("");
      setCaptchaError(
        err?.message || "We couldn't load the security check. Please try again."
      );
      setCaptchaStatus("error");
    }
  }, []);

  useEffect(() => {
    loadCaptcha();
    return () => {
      // Invalidate any in-flight request and abort it on unmount.
      captchaReqRef.current += 1;
      captchaAbortRef.current?.abort();
    };
  }, [loadCaptcha]);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetchJson("/api/public/leads", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          captcha_token: captcha.token,
          captcha_answer: captchaAnswer,
        }),
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Failed to submit request. Please verify your details.");
      // Challenges are single-use server-side, so a rejected/expired CAPTCHA
      // always needs a fresh one. Prefer the stable error code over message text.
      if (err?.code === "captcha_error" || /security check|captcha/i.test(err.message || "")) {
        loadCaptcha();
      }
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
            Book a 30-minute interactive session with our product experts to see how Silveri Hire can eliminate screening bottlenecks for your team.
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
                <p>Discover how much recruiter and engineering bandwidth Silveri Hire saves each week.</p>
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
              &ldquo;The demo showed us exactly how Silveri Hire would cut our technical phone screen load from 12 hours a week to zero.&rdquo;
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
                  maxLength={200}
                  required
                />
              </div>
              <div className="mkt-form-group">
                <label>Industry</label>
                <input
                  value={form.industry}
                  onChange={update("industry")}
                  placeholder="e.g. Fintech, Healthcare"
                  maxLength={100}
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
                  maxLength={120}
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
                  maxLength={254}
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
                  maxLength={30}
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
                  maxLength={5000}
                />
              </div>

              <div className="mkt-form-group">
                <label>Security Check *</label>
                <div className="mkt-captcha">
                  {captchaStatus === "ready" ? (
                    <>
                      <span className="mkt-captcha-question">
                        What is {captcha.question}
                      </span>
                      <input
                        type="text"
                        value={captchaAnswer}
                        onChange={(e) => setCaptchaAnswer(e.target.value)}
                        placeholder="Your answer"
                        maxLength={10}
                        autoComplete="off"
                        required
                      />
                      <button
                        type="button"
                        className="mkt-captcha-refresh"
                        onClick={loadCaptcha}
                        aria-label="New challenge"
                        title="New challenge"
                      >
                        <RefreshCw size={15} />
                      </button>
                    </>
                  ) : captchaStatus === "error" ? (
                    <>
                      <span className="mkt-captcha-question mkt-captcha-error" role="alert">
                        {captchaError}
                      </span>
                      <button
                        type="button"
                        className="mkt-captcha-refresh"
                        onClick={loadCaptcha}
                        aria-label="Retry security check"
                        title="Retry security check"
                      >
                        <RefreshCw size={15} />
                      </button>
                    </>
                  ) : (
                    <span className="mkt-captcha-question">
                      Loading security check...
                    </span>
                  )}
                </div>
              </div>

              <button
                type="submit"
                className="mkt-btn mkt-btn-primary mkt-btn-lg"
                disabled={loading || captchaStatus !== "ready"}
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
