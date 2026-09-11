import React from "react";
import { Link } from "react-router-dom";
import { Sparkles, ShieldCheck, ArrowRight } from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import "./marketing.css";

const SECTIONS = [
  {
    title: "1. Information We Collect",
    body: "HireAI collects information you provide directly to the platform, including company account details, team member information, candidate resumes, interview responses, recordings, and usage data. We also collect limited technical data such as device type and browser information to operate and secure the service.",
  },
  {
    title: "2. How We Use Your Information",
    body: "Your information is used to provide and improve the hiring platform, score and evaluate candidates, generate scorecards and audit logs, communicate with you about your account, and ensure the security and integrity of the platform and its users.",
  },
  {
    title: "3. Data Isolation & Security",
    body: "All company data is stored in a multi-tenant architecture and strictly isolated by company identifier. Access is protected by authentication and role-based permissions. We employ industry-standard safeguards, encryption in transit, and continuous monitoring to protect your data.",
  },
  {
    title: "4. Interview Recordings & Proctoring",
    body: "With candidate consent, the platform records interview audio and video, along with proctoring events, solely for evaluation and compliance purposes. Recordings are accessible only to authorized members of the hiring company and are retained according to your plan settings.",
  },
  {
    title: "5. Data Sharing",
    body: "We do not sell your personal data. Data is shared only with service providers that support platform operations under strict confidentiality obligations, or where required by applicable law.",
  },
  {
    title: "6. Your Rights",
    body: "Depending on your jurisdiction, you may have the right to access, correct, export, or delete your personal data. You may also withdraw consent for processing where applicable. To exercise these rights, contact us through the Book a Demo page.",
  },
  {
    title: "7. Data Retention",
    body: "We retain your data for as long as your account is active or as needed to provide the service, after which it is securely deleted or anonymized in line with applicable law.",
  },
  {
    title: "8. Changes to This Policy",
    body: "We may update this Privacy Policy from time to time. Material changes will be communicated through the platform or by email. Continued use of the platform after changes indicates acceptance of the updated policy.",
  },
  {
    title: "9. Contact Us",
    body: "For any privacy-related questions, requests, or concerns, please reach out through our Book a Demo page and our team will assist you promptly.",
  },
];

export function PrivacyPolicyPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <span className="mkt-eyebrow">
          <ShieldCheck size={13} /> Legal
        </span>
        <h1>Privacy Policy</h1>
        <p>Last updated: September 2026</p>
        <p>
          HireAI Platform Inc - Silveri Consulting Services Pvt Ltd is committed to protecting your privacy and the confidentiality of your hiring data.
        </p>
      </section>

      <div className="mkt-section" style={{ paddingTop: "1rem" }}>
        <div className="mkt-faq-grid">
          {SECTIONS.map((s) => (
            <div key={s.title} className="mkt-faq-item" style={{ padding: "1.75rem" }}>
              <h3 style={{ fontSize: "1.2rem", color: "#ffffff", marginBottom: "0.75rem" }}>{s.title}</h3>
              <p style={{ color: "var(--mkt-muted)", fontSize: "0.95rem", lineHeight: "1.7" }}>{s.body}</p>
            </div>
          ))}
        </div>
      </div>

      <section className="mkt-cta-band">
        <h2>Questions about your data?</h2>
        <p>Our team is happy to walk you through our security and privacy practices.</p>
        <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary mkt-btn-lg">
          Talk to our team <ArrowRight size={18} />
        </Link>
      </section>
    </MarketingLayout>
  );
}