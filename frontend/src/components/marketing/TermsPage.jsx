import React from "react";
import { Link } from "react-router-dom";
import { Sparkles, CheckCircle2, ArrowRight } from "lucide-react";
import { MarketingLayout } from "./MarketingLayout";
import "./marketing.css";

const SECTIONS = [
  {
    title: "1. Acceptance of Terms",
    body: "By accessing or using the HireAI platform, you agree to be bound by these Terms & Conditions and all applicable laws. If you do not agree with any part of these terms, you must not use the platform.",
  },
  {
    title: "2. Description of Service",
    body: "HireAI provides an AI-powered hiring platform that includes resume screening, live voice and video AI interviews, hiring pipeline management, proctoring, and related services, delivered as a subscription-based SaaS offering.",
  },
  {
    title: "3. Accounts & User Responsibilities",
    body: "You are responsible for maintaining the confidentiality of your account credentials and for all activity conducted under your account. You agree to provide accurate information and to use the platform in compliance with these terms and applicable law.",
  },
  {
    title: "4. Acceptable Use",
    body: "You agree not to misuse the platform, attempt unauthorized access, interfere with platform operations, or use the platform to collect data improperly. Automated scraping, reverse engineering, and reselling of platform access are prohibited.",
  },
  {
    title: "5. Subscription & Billing",
    body: "Paid plans are billed according to the pricing displayed on the platform. Fees are non-refundable except as required by law. We may update pricing with reasonable notice, and continued use after such changes constitutes acceptance.",
  },
  {
    title: "6. Intellectual Property",
    body: "The platform, including its software, design, branding, and AI models, is owned by HireAI Platform Inc and its licensors. No rights are granted beyond the limited license to use the service for your business purposes.",
  },
  {
    title: "7. Candidate Data & Compliance",
    body: "You are responsible for obtaining any necessary consents from candidates and for using the platform in compliance with applicable employment, data protection, and privacy laws.",
  },
  {
    title: "8. Limitation of Liability",
    body: "To the maximum extent permitted by law, HireAI shall not be liable for indirect, incidental, or consequential damages arising from your use of the platform. Our total liability is limited to the amounts paid by you in the twelve months preceding the claim.",
  },
  {
    title: "9. Termination",
    body: "Either party may terminate the subscription in accordance with the selected plan. We may suspend or terminate access for breach of these terms, material misconduct, or non-payment, with notice where feasible.",
  },
  {
    title: "10. Changes to Terms",
    body: "We may update these Terms & Conditions periodically. Material changes will be communicated through the platform. Continued use of the platform after changes are posted constitutes acceptance of the revised terms.",
  },
  {
    title: "11. Governing Law",
    body: "These terms are governed by the applicable laws of the jurisdiction in which HireAI Platform Inc operates, without regard to conflict-of-law principles.",
  },
  {
    title: "12. Contact Us",
    body: "Questions about these Terms & Conditions can be directed through our Book a Demo page and our team will respond as soon as possible.",
  },
];

export function TermsPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <span className="mkt-eyebrow">
          <CheckCircle2 size={13} /> Legal
        </span>
        <h1>Terms &amp; Conditions</h1>
        <p>Last updated: September 2026</p>
        <p>
          These terms govern your access to and use of the HireAI platform, operated by HireAI Platform Inc - Silveri Consulting Services Pvt Ltd.
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
        <h2>Have questions about these terms?</h2>
        <p>Reach out to our team and we will be happy to clarify.</p>
        <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary mkt-btn-lg">
          Contact us <ArrowRight size={18} />
        </Link>
      </section>
    </MarketingLayout>
  );
}