import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Sparkles, ArrowRight, ShieldCheck, HelpCircle } from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import { apiFetchJson } from "../../utils/api";
import "./marketing.css";

const FALLBACK_PLANS = [
  {
    id: "starter",
    label: "Starter",
    max_users: 5,
    max_jobs: 3,
    max_credits: 500,
    price: 199,
    desc: "For growing startups establishing a structured hiring pipeline.",
  },
  {
    id: "growth",
    label: "Growth",
    max_users: 15,
    max_jobs: 10,
    max_credits: 2000,
    price: 499,
    desc: "For scaling engineering and talent acquisition teams with high volume.",
  },
  {
    id: "enterprise",
    label: "Enterprise",
    max_users: 50,
    max_jobs: 50,
    max_credits: 10000,
    price: null,
    desc: "For large organizations requiring custom SLAs, dedicated support & quotas.",
  },
];

const PLAN_FEATURES = {
  starter: [
    "Up to 5 team seats",
    "3 active job drives",
    "500 AI credits / month",
    "AI Resume Parsing & Scoring",
    "Live Voice AI Technical Interviews",
    "Visual Hiring Pipeline",
    "Standard Email Support",
  ],
  growth: [
    "Up to 15 team seats",
    "10 active job drives",
    "2,000 AI credits / month",
    "AI Resume Parsing & Scoring",
    "Live Voice AI Technical & HR Rounds",
    "Anti-Cheating & Focus Proctoring",
    "Custom Question Banks",
    "Team Role Permissions (RBAC)",
    "Priority Support & Onboarding",
  ],
  enterprise: [
    "50+ team seats (Custom limits)",
    "50+ active job drives",
    "10,000+ AI credits / month",
    "Dedicated Multi-Tenant Isolation",
    "Custom AI Scoring Weights",
    "Full Compliance Audit Trail Export",
    "Custom ATS & HRIS Integrations",
    "Dedicated Success Manager & SLA",
  ],
};

export function PricingPage() {
  const [plans, setPlans] = useState(FALLBACK_PLANS);
  const [isAnnual, setIsAnnual] = useState(false);

  useEffect(() => {
    apiFetchJson("/api/public/plans")
      .then((data) => {
        if (data.plans?.length) {
          // Merge API data with rich descriptions
          const merged = data.plans.map((p) => {
            const fallback = FALLBACK_PLANS.find((f) => f.id === p.id);
            return {
              ...p,
              desc: fallback?.desc || "Complete AI hiring suite with full feature access.",
            };
          });
          setPlans(merged);
        }
      })
      .catch(() => {});
  }, []);

  function getDisplayedPrice(price) {
    if (price == null || price === "") return "Custom";
    const num = Number(price);
    const finalPrice = isAnnual ? Math.round(num * 0.8) : num;
    return `$${finalPrice.toLocaleString()}`;
  }

  return (
    <MarketingLayout>
      {/* ── Page Hero ──────────────────────────────────────────────────── */}
      <section className="mkt-page-hero" style={{ padding: "4rem 2rem 2.5rem", textAlign: "center", maxWidth: "800px", margin: "0 auto" }}>
        <span className="mkt-eyebrow">
          <Sparkles size={13} /> Transparent Pricing
        </span>
        <h1 style={{ fontSize: "3.2rem", fontWeight: "800", letterSpacing: "-0.03em", marginBottom: "1rem" }}>
          Simple plans that scale with your team
        </h1>
        <p className="page-subtitle" style={{ fontSize: "1.15rem", color: "var(--mkt-muted)", lineHeight: "1.7" }}>
          No hidden fees. Every plan includes AI resume screening, live voice interviewing, and pipeline management.
        </p>
      </section>

      {/* ── Billing Cycle Toggle ────────────────────────────────────────── */}
      <div className="mkt-pricing-toggle">
        <span
          className={`mkt-toggle-label ${!isAnnual ? "active" : ""}`}
          onClick={() => setIsAnnual(false)}
        >
          Monthly Billing
        </span>
        <div
          className={`mkt-toggle-switch ${isAnnual ? "annual" : ""}`}
          onClick={() => setIsAnnual(!isAnnual)}
          role="button"
          tabIndex={0}
          aria-label="Toggle Annual Billing"
        >
          <div className="mkt-toggle-thumb" />
        </div>
        <span
          className={`mkt-toggle-label ${isAnnual ? "active" : ""}`}
          onClick={() => setIsAnnual(true)}
        >
          Annual Billing
        </span>
        <span className="mkt-discount-badge">Save 20%</span>
      </div>

      {/* ── Pricing Cards Grid ──────────────────────────────────────────── */}
      <div className="mkt-section" style={{ paddingTop: 0 }}>
        <div className="mkt-pricing-grid">
          {plans.map((plan, idx) => {
            const isFeatured = idx === 1 || plan.id === "growth";
            const features = PLAN_FEATURES[plan.id] || PLAN_FEATURES.growth;

            return (
              <div
                key={plan.id}
                className={`mkt-pricing-card ${isFeatured ? "featured" : ""}`}
              >
                {isFeatured && (
                  <span className="mkt-popular-tag">
                    <Sparkles size={12} style={{ display: "inline", marginRight: "4px" }} />
                    Most Popular
                  </span>
                )}
                <h3>{plan.label}</h3>
                <p className="mkt-pricing-desc">{plan.desc}</p>

                <div className="mkt-pricing-price">
                  {getDisplayedPrice(plan.price)}
                  {plan.price != null && <span> / month</span>}
                </div>

                <ul className="mkt-pricing-features">
                  {features.map((feat) => (
                    <li key={feat}>
                      <Check size={16} className="tick" />
                      <span>{feat}</span>
                    </li>
                  ))}
                </ul>

                <Link
                  to={`/book-a-demo?plan=${plan.id}`}
                  className={`mkt-btn ${isFeatured ? "mkt-btn-primary" : "mkt-btn-secondary"} mkt-btn-lg`}
                >
                  {plan.price != null ? "Get Started" : "Talk to Sales"} <ArrowRight size={16} />
                </Link>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Enterprise Trust Banner ─────────────────────────────────────── */}
      <div className="mkt-trust-strip" style={{ marginTop: "3rem" }}>
        <p>Enterprise Guarantees &amp; Compliance</p>
        <div className="mkt-trust-logos">
          <div className="mkt-trust-logo-item"><ShieldCheck size={18} color="#2dd4bf" /> SOC-2 Type II Ready</div>
          <div className="mkt-trust-logo-item"><ShieldCheck size={18} color="#2dd4bf" /> GDPR Compliant</div>
          <div className="mkt-trust-logo-item"><ShieldCheck size={18} color="#2dd4bf" /> 99.9% Uptime SLA</div>
          <div className="mkt-trust-logo-item"><ShieldCheck size={18} color="#2dd4bf" /> Dedicated Multi-Tenant Storage</div>
        </div>
      </div>
    </MarketingLayout>
  );
}
