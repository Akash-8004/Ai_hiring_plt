import React, { useState } from "react";
import { Link } from "react-router-dom";
import {
  Sparkles, FileSearch, Mic, GitBranch, Users, Shield,
  Building2, Rocket, Landmark, GraduationCap, Briefcase,
  ArrowRight, CheckCircle2, ChevronDown, Star, Play, Check,
  Cpu, Terminal, Layers, Lock, BarChart3, Clock, HelpCircle,
} from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import "./marketing.css";

const FEATURES = [
  {
    icon: FileSearch,
    title: "AI Resume Shortlisting",
    desc: "Parse TXT, PDF, and DOCX resumes instantly. The AI scores candidates against your job description and threshold criteria.",
    tags: ["Automated Scoring", "Skill Extraction", "Custom Thresholds"],
  },
  {
    icon: Mic,
    title: "Live Voice AI Interviews",
    desc: "Conduct HR and technical rounds with live AI. Candidate responses are transcribed in real-time and evaluated automatically.",
    tags: ["Real-Time Speech", "Live Transcription", "Auto-Scorecards"],
  },
  {
    icon: GitBranch,
    title: "Visual Hiring Pipeline",
    desc: "Track every candidate across intake, shortlisting, technical evaluation, and offer stages with drag-and-drop clarity.",
    tags: ["Kanban View", "Stage Transitions", "Candidate Dossier"],
  },
  {
    icon: Users,
    title: "Team Access & Seat Management",
    desc: "Company admins assign seats and fine-grained permissions (HR, Interviewer, Recruiter) up to their plan limits.",
    tags: ["RBAC Permissions", "Self-Serve Seats", "Company Isolation"],
  },
  {
    icon: Shield,
    title: "Enterprise Anti-Cheat & Proctoring",
    desc: "Active window blur tracking, tab-switch logging, proctoring events, and an immutable audit log for compliance.",
    tags: ["Proctoring Events", "Integrity Logs", "JWT Auth"],
  },
  {
    icon: Sparkles,
    title: "Multi-Tenant SaaS Architecture",
    desc: "Super Admin, Company Admin, and Staff tiers. Data is strictly isolated by company_id in high-availability MongoDB.",
    tags: ["Data Isolation", "Usage Credits", "Enterprise SLAs"],
  },
];

const TAB_PRODUCTS = [
  {
    id: "screening",
    label: "Resume Screening",
    icon: FileSearch,
    title: "Zero-bias, lightning-fast resume evaluation",
    desc: "Upload hundreds of resumes in batch. HireAI extracts skills, work experience, and educational background, scoring candidates against your drive's exact benchmark.",
    bullets: [
      "Multi-format parsing: PDF, DOCX, TXT",
      "Configurable match thresholds (e.g. 75%+ for automatic invite)",
      "Instant shortlist vs. rejected classification with explanations",
    ],
    preview: {
      type: "screening",
      candidate: "Sarah Chen",
      role: "Staff Backend Engineer",
      match: "94%",
      matchedSkills: ["Python", "FastAPI", "Distributed Systems", "PostgreSQL"],
      verdict: "Recommended for Technical Round",
    },
  },
  {
    id: "voice",
    label: "Live Voice AI",
    icon: Mic,
    title: "Autonomous 2-way voice technical interviews",
    desc: "Candidates enter a browser-based interview room where live AI conducts adaptive HR and coding rounds. Natural voice feedback, live question follow-ups, and auto-transcription.",
    bullets: [
      "Integrated audio streaming directly in browser (no download)",
      "Adaptive technical probing based on candidate answers",
      "Full conversation audio recording and instant transcript export",
    ],
    preview: {
      type: "voice",
      interviewer: "HireAI Technical Agent",
      round: "System Design & Concurrency",
      status: "Live Recording",
      question: "How would you design a distributed rate limiter for a high-traffic API gateway?",
    },
  },
  {
    id: "pipeline",
    label: "Hiring Pipeline",
    icon: GitBranch,
    title: "End-to-end recruitment lifecycle in one place",
    desc: "Move candidates seamlessly from intake to scheduled interviews, scorecards, and final hiring decisions with complete team collaboration.",
    bullets: [
      "Customizable hiring stages for different departments",
      "One-click invite links with expiration tokens",
      "Comprehensive candidate profile with score history and feedback",
    ],
    preview: {
      type: "pipeline",
      stats: [
        { stage: "Applied", count: 142 },
        { stage: "Shortlisted", count: 38 },
        { stage: "AI Interview", count: 18 },
        { stage: "Offer", count: 4 },
      ],
    },
  },
  {
    id: "security",
    label: "Enterprise Security",
    icon: Shield,
    title: "Enterprise-grade isolation and compliance",
    desc: "Built from the ground up for strict enterprise requirements. Multi-tenant database separation, tamper-proof activity audit trails, and strict role permissions.",
    bullets: [
      "Multi-tenant data isolation per company identifier",
      "Detailed audit logging for every candidate action and seat change",
      "JWT-authenticated secure access with role-based restrictions",
    ],
    preview: {
      type: "security",
      checks: [
        { name: "Tenant Data Isolation", status: "Active" },
        { name: "Audit Trail Logging", status: "100% Monitored" },
        { name: "Proctoring Integrity", status: "Enforced" },
      ],
    },
  },
];

const STEPS = [
  {
    step: "01",
    title: "Create a Job Drive",
    desc: "Specify required skills, experience levels, and custom coding or domain-specific questions.",
  },
  {
    step: "02",
    title: "Upload & Auto-Screen",
    desc: "Upload resumes in bulk. The AI parses and scores applicants against your benchmark.",
  },
  {
    step: "03",
    title: "Conduct Voice AI Rounds",
    desc: "Shortlisted candidates receive secure links for interactive voice-based technical and HR interviews.",
  },
  {
    step: "04",
    title: "Review & Confident Hire",
    desc: "Inspect candidate scorecards, transcribed dialogues, and proctoring logs to make the final hire.",
  },
];

const SOLUTIONS = [
  {
    icon: Building2,
    title: "HR & Talent Acquisition",
    desc: "Automate resume screening, eliminate manual phone screens, and achieve consistent candidate evaluations.",
  },
  {
    icon: Rocket,
    title: "Engineering Leaders & CTOs",
    desc: "Save hundreds of engineering hours with AI-driven technical assessments and live coding evaluation.",
  },
  {
    icon: Briefcase,
    title: "High-Growth Startups",
    desc: "Deploy a scalable, world-class hiring process from day one without needing an army of recruiters.",
  },
  {
    icon: Landmark,
    title: "Enterprises",
    desc: "Multi-tenant access control, customized credit quotas, permission management, and comprehensive audit logs.",
  },
  {
    icon: GraduationCap,
    title: "University Drives",
    desc: "Screen thousands of campus applicants simultaneously with standardized, repeatable AI scoring.",
  },
];

const TESTIMONIALS = [
  {
    quote: "HireAI slashed our engineering screening time by 75%. Our senior engineers now only spend time on final culture interviews with top-tier candidates.",
    author: "Alex Rivera",
    role: "VP of Engineering, CloudScale",
    avatar: "AR",
    rating: 5,
  },
  {
    quote: "The live voice AI interviews feel incredibly natural. Candidates love the flexible 24/7 scheduling, and our team receives objective, structured scorecards.",
    author: "Elena Rostova",
    role: "Head of Talent, Finova Tech",
    avatar: "ER",
    rating: 5,
  },
  {
    quote: "The multi-tenant architecture and credit system allow us to manage hiring for 12 business units with full audit trails and security isolation.",
    author: "David Vance",
    role: "Global HR Director, Apex Enterprise",
    avatar: "DV",
    rating: 5,
  },
];

const FAQS = [
  {
    q: "How does the live voice AI interview work?",
    a: "Candidates open a secure browser link with no extra downloads needed. HireAI connects their microphone to a real-time AI interviewer that asks structured technical and behavioral questions, reacts naturally to responses, transcribes the conversation, and generates a structured scorecard.",
  },
  {
    q: "How does AI resume screening evaluate candidates?",
    a: "When resumes (PDF, DOCX, TXT) are uploaded, HireAI extracts candidate skills, experience duration, and project history. It scores each resume against the specific job drive requirements and automatically categorizes applicants into shortlisted or rejected based on your configured threshold.",
  },
  {
    q: "What anti-cheating and proctoring measures are in place?",
    a: "The platform tracks candidate window focus loss, tab switching, and interview environment anomalies. Every event is logged with timestamps and included in the candidate's final evaluation dossier for recruiter review.",
  },
  {
    q: "Can we customize job criteria and interview questions?",
    a: "Yes! When creating a job drive, you can specify custom required skills, minimum experience years, education requirements, and add custom coding or behavioral interview questions.",
  },
  {
    q: "How is company data isolated and secured?",
    a: "HireAI uses a multi-tenant database design where all resumes, candidate evaluations, and job drives are strictly partitioned by company_id. Platform access is guarded by JWT authentication and granular role-based permissions.",
  },
];

export function LandingPage() {
  const [activeTabId, setActiveTabId] = useState("screening");
  const [openFaq, setOpenFaq] = useState(null);

  const activeTab = TAB_PRODUCTS.find((t) => t.id === activeTabId) || TAB_PRODUCTS[0];

  const toggleFaq = (idx) => {
    setOpenFaq((curr) => (curr === idx ? null : idx));
  };

  return (
    <MarketingLayout>
      {/* ── Hero Section ────────────────────────────────────────────────── */}
      <section className="mkt-hero">
        <div>
          <div className="mkt-hero-badge">
            <span className="mkt-live-dot" />
            <span>Next-Gen AI Technical &amp; HR Hiring Platform</span>
          </div>

          <h1>
            Enterprise hiring, <span className="grad">confidently.</span>
          </h1>

          <p className="mkt-hero-sub">
            HireAI unites intelligent resume screening, live voice AI interviews, and an end-to-end hiring pipeline — empowering your team to hire top talent 3x faster with zero bias.
          </p>

          <div className="mkt-hero-cta">
            <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary mkt-btn-lg">
              Book a live demo <ArrowRight size={18} />
            </Link>
            <Link to="/pricing" className="mkt-btn mkt-btn-secondary mkt-btn-lg">
              Explore plans &amp; pricing
            </Link>
          </div>

          <div className="mkt-hero-metrics">
            <div className="mkt-metric-pill">
              <strong>10,000+</strong>
              <span>Interviews Ran</span>
            </div>
            <div className="mkt-metric-pill">
              <strong>85%</strong>
              <span>Time Saved</span>
            </div>
            <div className="mkt-metric-pill">
              <strong>99.8%</strong>
              <span>Uptime SLA</span>
            </div>
          </div>
        </div>

        {/* Hero Interactive-Feeling Preview Widget */}
        <div className="mkt-hero-widget">
          <div className="mkt-widget-header">
            <div className="mkt-widget-dots">
              <span />
              <span />
              <span />
            </div>
            <div className="mkt-widget-tag">
              <span className="mkt-live-dot" /> Live Voice AI
            </div>
          </div>

          {/* Voice Room Live Card */}
          <div className="mkt-voice-live-card">
            <div className="mkt-voice-avatar">
              <Mic size={22} />
            </div>
            <div className="mkt-voice-info">
              <div className="mkt-voice-info-head">
                <span className="mkt-voice-title">Technical Interview: Sarah Chen</span>
                <div className="mkt-audio-bars">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
              </div>
              <p className="mkt-voice-transcript">
                &ldquo;Explain how you would optimize a distributed cache to prevent stampede under high load...&rdquo;
              </p>
            </div>
          </div>

          {/* Candidate Scorecard Preview */}
          <div className="mkt-candidate-score-card">
            <div className="mkt-candidate-head">
              <div className="mkt-candidate-user">
                <div className="mkt-candidate-avatar">SC</div>
                <div>
                  <div className="mkt-candidate-name">Sarah Chen</div>
                  <div className="mkt-candidate-role">Senior Full-Stack Engineer</div>
                </div>
              </div>
              <div className="mkt-score-badge">
                <CheckCircle2 size={16} /> 94% Match
              </div>
            </div>

            <div className="mkt-skill-meters">
              <div className="mkt-meter-row">
                <span className="mkt-meter-label">System Design</span>
                <div className="mkt-meter-bar">
                  <div className="mkt-meter-fill" style={{ width: "95%" }} />
                </div>
                <span className="mkt-meter-val">95%</span>
              </div>
              <div className="mkt-meter-row">
                <span className="mkt-meter-label">Python &amp; Node</span>
                <div className="mkt-meter-bar">
                  <div className="mkt-meter-fill" style={{ width: "92%" }} />
                </div>
                <span className="mkt-meter-val">92%</span>
              </div>
              <div className="mkt-meter-row">
                <span className="mkt-meter-label">Problem Solving</span>
                <div className="mkt-meter-bar">
                  <div className="mkt-meter-fill" style={{ width: "90%" }} />
                </div>
                <span className="mkt-meter-val">90%</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Trust Strip ─────────────────────────────────────────────────── */}
      <div className="mkt-trust-strip">
        <p>Trusted by engineering, talent acquisition &amp; enterprise leaders</p>
        <div className="mkt-trust-logos">
          <div className="mkt-trust-logo-item">
            <Cpu size={20} color="#38bdf8" /> CloudScale Global
          </div>
          <div className="mkt-trust-logo-item">
            <Layers size={20} color="#2dd4bf" /> Fintech Labs
          </div>
          <div className="mkt-trust-logo-item">
            <Terminal size={20} color="#818cf8" /> DevEngine Inc
          </div>
          <div className="mkt-trust-logo-item">
            <Building2 size={20} color="#a78bfa" /> Nexus Enterprise
          </div>
          <div className="mkt-trust-logo-item">
            <Lock size={20} color="#34d399" /> CyberSecure Systems
          </div>
        </div>
      </div>

      {/* ── Interactive Product Tabs ("What HireAI does") ────────────────── */}
      <section id="why" className="mkt-section">
        <div className="mkt-section-header">
          <span className="mkt-eyebrow">
            <Sparkles size={13} /> Complete Hiring Suite
          </span>
          <h2>What HireAI does</h2>
          <p>
            An end-to-end hiring operating system built to automate screening, conduct technical interviews, and streamline team decisions.
          </p>
        </div>

        {/* Tab Buttons */}
        <div className="mkt-tabs-nav">
          {TAB_PRODUCTS.map((t) => (
            <button
              key={t.id}
              className={`mkt-tab-btn ${activeTabId === t.id ? "active" : ""}`}
              onClick={() => setActiveTabId(t.id)}
            >
              <t.icon size={18} />
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        {/* Active Tab Showcase Box */}
        <div className="mkt-tab-content-box">
          <div className="mkt-tab-desc">
            <h3>{activeTab.title}</h3>
            <p>{activeTab.desc}</p>
            <ul className="mkt-tab-features">
              {activeTab.bullets.map((b) => (
                <li key={b}>
                  <CheckCircle2 size={18} className="check-icon" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
            <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary">
              See this in action <ArrowRight size={16} />
            </Link>
          </div>

          <div className="mkt-tab-preview">
            {activeTab.preview.type === "screening" && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                  <div style={{ fontWeight: "700", color: "#ffffff", fontSize: "1.1rem" }}>
                    Candidate Scorecard: {activeTab.preview.candidate}
                  </div>
                  <span className="mkt-score-badge">{activeTab.preview.match}</span>
                </div>
                <div style={{ fontSize: "0.85rem", color: "var(--mkt-muted)", marginBottom: "1rem" }}>
                  Role: <strong style={{ color: "#ffffff" }}>{activeTab.preview.role}</strong>
                </div>
                <div style={{ marginBottom: "1.25rem" }}>
                  <div style={{ fontSize: "0.78rem", color: "var(--mkt-muted-dim)", textTransform: "uppercase", marginBottom: "0.5rem", fontWeight: 700 }}>
                    Skills Verified by AI
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {activeTab.preview.matchedSkills.map((s) => (
                      <span key={s} className="mkt-feature-tag" style={{ background: "rgba(59, 130, 246, 0.15)", color: "#93c5fd", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                        ✓ {s}
                      </span>
                    ))}
                  </div>
                </div>
                <div style={{ padding: "0.75rem 1rem", background: "rgba(20, 184, 166, 0.1)", border: "1px solid rgba(20, 184, 166, 0.3)", borderRadius: "8px", fontSize: "0.85rem", color: "#2dd4bf", fontWeight: 600 }}>
                  ⚡ {activeTab.preview.verdict}
                </div>
              </div>
            )}

            {activeTab.preview.type === "voice" && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                  <div style={{ fontWeight: "700", color: "#ffffff" }}>
                    {activeTab.preview.round}
                  </div>
                  <span className="mkt-widget-tag">
                    <span className="mkt-live-dot" /> {activeTab.preview.status}
                  </span>
                </div>
                <div style={{ background: "rgba(255, 255, 255, 0.04)", padding: "1.1rem", borderRadius: "10px", border: "1px solid var(--mkt-border)", marginBottom: "1rem" }}>
                  <div style={{ fontSize: "0.75rem", color: "#60a5fa", fontWeight: 700, textTransform: "uppercase", marginBottom: "0.4rem" }}>
                    Live AI Prompt
                  </div>
                  <p style={{ color: "#e2e8f0", fontSize: "0.92rem", fontStyle: "italic", margin: 0 }}>
                    &ldquo;{activeTab.preview.question}&rdquo;
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.82rem", color: "var(--mkt-muted)" }}>
                  <span>Live AI Audio Relay</span>
                  <span style={{ color: "#34d399", fontWeight: 600 }}>Latency &lt; 280ms</span>
                </div>
              </div>
            )}

            {activeTab.preview.type === "pipeline" && (
              <div>
                <div style={{ fontWeight: "700", color: "#ffffff", marginBottom: "1.25rem" }}>
                  Active Job Drive: Senior Backend Engineer
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.85rem" }}>
                  {activeTab.preview.stats.map((st) => (
                    <div key={st.stage} style={{ background: "rgba(255, 255, 255, 0.03)", padding: "1rem", borderRadius: "10px", border: "1px solid var(--mkt-border)" }}>
                      <div style={{ fontSize: "0.78rem", color: "var(--mkt-muted)", marginBottom: "4px" }}>{st.stage}</div>
                      <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#ffffff" }}>{st.count}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab.preview.type === "security" && (
              <div>
                <div style={{ fontWeight: "700", color: "#ffffff", marginBottom: "1.25rem" }}>
                  Enterprise Compliance &amp; Multi-Tenant Guardrails
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {activeTab.preview.checks.map((chk) => (
                    <div key={chk.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.85rem 1rem", background: "rgba(255, 255, 255, 0.03)", border: "1px solid var(--mkt-border)", borderRadius: "8px" }}>
                      <span style={{ color: "#ffffff", fontSize: "0.9rem", fontWeight: 500 }}>{chk.name}</span>
                      <span style={{ color: "#2dd4bf", fontSize: "0.8rem", fontWeight: 700 }}>✓ {chk.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Feature Cards Grid ──────────────────────────────────────────── */}
      <section className="mkt-section" style={{ paddingTop: "0" }}>
        <div className="mkt-features-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="mkt-feature-card">
              <div className="mkt-feature-icon">
                <f.icon size={24} />
              </div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
              <div className="mkt-feature-badges">
                {f.tags.map((t) => (
                  <span key={t} className="mkt-feature-tag">{t}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Performance Stats Band ──────────────────────────────────────── */}
      <div className="mkt-stats-band">
        <div className="mkt-stats-grid">
          <div>
            <div className="mkt-stat-value">3x</div>
            <div className="mkt-stat-label">Faster Time-to-Hire</div>
            <div className="mkt-stat-sub">From application to interview</div>
          </div>
          <div>
            <div className="mkt-stat-value">83%</div>
            <div className="mkt-stat-label">Less Manual Screening</div>
            <div className="mkt-stat-sub">Automated skill scoring</div>
          </div>
          <div>
            <div className="mkt-stat-value">100%</div>
            <div className="mkt-stat-label">Audit Trail Logged</div>
            <div className="mkt-stat-sub">Full proctoring &amp; RBAC logs</div>
          </div>
          <div>
            <div className="mkt-stat-value">4.9/5</div>
            <div className="mkt-stat-label">Candidate Experience</div>
            <div className="mkt-stat-sub">Flexible 24/7 interviews</div>
          </div>
        </div>
      </div>

      {/* ── 4-Step "How it works" ───────────────────────────────────────── */}
      <section id="how" className="mkt-section">
        <div className="mkt-section-header">
          <span className="mkt-eyebrow">
            <Clock size={13} /> Intuitive Workflow
          </span>
          <h2>From job drive to hire in four steps</h2>
          <p>
            Simple for recruiters, intuitive for candidates, and powerful for hiring managers.
          </p>
        </div>

        <div className="mkt-steps">
          {STEPS.map((s) => (
            <div key={s.title} className="mkt-step">
              <div className="mkt-step-num">{s.step}</div>
              <h4>{s.title}</h4>
              <p>{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Solutions Band ──────────────────────────────────────────────── */}
      <section id="solutions" className="mkt-section" style={{ paddingTop: 0 }}>
        <div className="mkt-section-header">
          <span className="mkt-eyebrow">
            <Users size={13} /> Built for Every Team
          </span>
          <h2>Tailored for your hiring scale</h2>
          <p>
            Whether you are an early-stage startup or a multi-department enterprise, HireAI scales with you.
          </p>
        </div>

        <div className="mkt-solutions">
          {SOLUTIONS.map((s) => (
            <div key={s.title} className="mkt-solution-card">
              <div className="sol-icon">
                <s.icon size={24} />
              </div>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Testimonials ────────────────────────────────────────────────── */}
      <section className="mkt-section mkt-testimonial-band">
        <div className="mkt-section-header">
          <span className="mkt-eyebrow">
            <Star size={13} /> Customer Reviews
          </span>
          <h2>Trusted by high-velocity teams</h2>
          <p>See how companies transform their hiring outcomes with HireAI.</p>
        </div>

        <div className="mkt-testimonials">
          {TESTIMONIALS.map((t) => (
            <div key={t.author} className="mkt-testimonial">
              <div>
                <div className="mkt-testimonial-stars">
                  {[...Array(t.rating)].map((_, i) => (
                    <Star key={i} size={16} fill="#f59e0b" color="#f59e0b" />
                  ))}
                </div>
                <p>&ldquo;{t.quote}&rdquo;</p>
              </div>

              <div className="mkt-testimonial-author-box">
                <div className="mkt-testimonial-avatar">{t.avatar}</div>
                <div>
                  <div className="mkt-testimonial-author">{t.author}</div>
                  <div className="mkt-testimonial-role">{t.role}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ Section ─────────────────────────────────────────────────── */}
      <section id="faq" className="mkt-section">
        <div className="mkt-section-header">
          <span className="mkt-eyebrow">
            <HelpCircle size={13} /> Got Questions?
          </span>
          <h2>Frequently Asked Questions</h2>
          <p>Everything you need to know about the HireAI platform and integrations.</p>
        </div>

        <div className="mkt-faq-grid">
          {FAQS.map((faq, idx) => (
            <div key={faq.q} className={`mkt-faq-item ${openFaq === idx ? "open" : ""}`}>
              <button className="mkt-faq-question" onClick={() => toggleFaq(idx)}>
                <span>{faq.q}</span>
                <ChevronDown size={18} className="chev" style={{ transform: openFaq === idx ? "rotate(180deg)" : "rotate(0)" }} />
              </button>
              {openFaq === idx && (
                <div className="mkt-faq-answer">
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ──────────────────────────────────────────────────── */}
      <section className="mkt-cta-band">
        <h2>Ready to transform your hiring pipeline?</h2>
        <p>
          Experience intelligent screening, autonomous voice interviews, and structured scorecards with zero friction.
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary mkt-btn-lg">
            Schedule a customized demo <ArrowRight size={18} />
          </Link>
          <Link to="/pricing" className="mkt-btn mkt-btn-secondary mkt-btn-lg">
            View transparent plans
          </Link>
        </div>
      </section>
    </MarketingLayout>
  );
}
