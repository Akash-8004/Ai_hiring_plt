import React from "react";
import { Link } from "react-router-dom";
import {
  Building2, FileSearch, Briefcase, GitBranch, Mail, Mic,
  Users, Shield, BarChart3, ClipboardList, Sparkles, CheckCircle2,
  ArrowRight, Lock, Terminal, Cpu, Clock, Check,
} from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import "./marketing.css";

const FEATURE_CATEGORIES = [
  {
    category: "AI Resume Screening & Intake",
    eyebrow: "Intelligent Ingestion",
    desc: "Parse unstructured resumes at scale with deep semantic skill extraction and customizable score thresholds.",
    items: [
      {
        icon: FileSearch,
        title: "Multi-Format Resume Ingestion",
        desc: "Upload PDF, DOCX, and TXT resumes individually or in batch. Also supports manual candidate profile entry.",
      },
      {
        icon: Cpu,
        title: "Semantic Skill Scoring",
        desc: "Powered by advanced AI with a robust local fallback to ensure 100% processing reliability.",
      },
      {
        icon: CheckCircle2,
        title: "Custom Match Thresholds",
        desc: "Configure exact passing percentages per job drive to filter candidates automatically into shortlisted vs. rejected.",
      },
    ],
  },
  {
    category: "Live Voice AI Interviewing",
    eyebrow: "Live AI Relay",
    desc: "Browser-native 2-way conversational voice interviews that evaluate technical problem solving and communication.",
    items: [
      {
        icon: Mic,
        title: "Real-Time 2-Way Voice Rounds",
        desc: "Interactive technical and HR interviews with ultra-low latency audio streaming directly in candidate browsers.",
      },
      {
        icon: Terminal,
        title: "Adaptive Technical Questioning",
        desc: "The AI interviewer probes deeper based on candidate responses, asking follow-ups and edge-case questions.",
      },
      {
        icon: ClipboardList,
        title: "Auto-Transcription & Recordings",
        desc: "Full conversation transcripts are saved and structured scorecards are automatically generated on session completion.",
      },
    ],
  },
  {
    category: "Anti-Cheating & Proctoring",
    eyebrow: "Assessment Integrity",
    desc: "Comprehensive proctoring monitors candidate focus and flags suspicious behavior without invading privacy.",
    items: [
      {
        icon: Shield,
        title: "Window Blur & Focus Tracking",
        desc: "Monitors Alt+Tab, window minimization, and background tab switches with precise event timestamps.",
      },
      {
        icon: Lock,
        title: "Tamper-Proof Audit Dossier",
        desc: "Proctoring flags and timeline events are bundled into the candidate scorecard for recruiter review.",
      },
      {
        icon: Clock,
        title: "Session Expiration & Secure Tokens",
        desc: "Single-use secure interview links protect against unauthorized test sharing or re-entry.",
      },
    ],
  },
  {
    category: "Pipeline & Multi-Tenant SaaS",
    eyebrow: "Enterprise Infrastructure",
    desc: "Role-based seats, usage credit tracking, and isolated multi-tenant environments.",
    items: [
      {
        icon: GitBranch,
        title: "Visual Hiring Pipeline",
        desc: "Kanban-style tracking from intake to invite, live interview, and final offer with candidate status filters.",
      },
      {
        icon: Users,
        title: "Self-Serve Seat Management",
        desc: "Company admins can invite hiring managers, interviewers, and HR staff with granular RBAC permissions.",
      },
      {
        icon: BarChart3,
        title: "Credit Quotas & Governance",
        desc: "Transparent interview credit consumption per plan with real-time usage meters and billing controls.",
      },
    ],
  },
];

export function FeaturesPage() {
  return (
    <MarketingLayout>
      {/* ── Page Hero ──────────────────────────────────────────────────── */}
      <section className="mkt-page-hero" style={{ padding: "4rem 2rem 2rem", textAlign: "center", maxWidth: "800px", margin: "0 auto" }}>
        <span className="mkt-eyebrow">
          <Sparkles size={13} /> Complete Feature Directory
        </span>
        <h1 style={{ fontSize: "3.2rem", fontWeight: "800", letterSpacing: "-0.03em", marginBottom: "1rem" }}>
          Engineered for high-integrity, high-velocity hiring
        </h1>
        <p className="page-subtitle" style={{ fontSize: "1.15rem", color: "var(--mkt-muted)", lineHeight: "1.7" }}>
          Discover every enterprise capability built into HireAI — from multi-modal AI screening to autonomous voice interviews.
        </p>
      </section>

      {/* ── Categories Sections ────────────────────────────────────────── */}
      <div className="mkt-section" style={{ paddingTop: "2rem" }}>
        {FEATURE_CATEGORIES.map((cat, idx) => (
          <div key={cat.category} style={{ marginBottom: "5rem" }}>
            <div style={{ marginBottom: "2rem" }}>
              <span className="mkt-eyebrow">{cat.eyebrow}</span>
              <h2 style={{ fontSize: "2.2rem", fontWeight: "800", color: "#ffffff", marginBottom: "0.5rem" }}>
                {cat.category}
              </h2>
              <p style={{ color: "var(--mkt-muted)", fontSize: "1.05rem", maxWidth: "680px" }}>
                {cat.desc}
              </p>
            </div>

            <div className="mkt-features-grid">
              {cat.items.map((item) => (
                <div key={item.title} className="mkt-feature-card">
                  <div className="mkt-feature-icon">
                    <item.icon size={24} />
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* ── CTA Banner ──────────────────────────────────────────────────── */}
      <section className="mkt-cta-band">
        <h2>Experience all features in a live environment</h2>
        <p>Get a personalized 30-minute demonstration with our product specialists.</p>
        <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary mkt-btn-lg">
          Book your demo today <ArrowRight size={18} />
        </Link>
      </section>
    </MarketingLayout>
  );
}
