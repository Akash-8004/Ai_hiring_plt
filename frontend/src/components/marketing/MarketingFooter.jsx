import React from "react";
import { Link } from "react-router-dom";
import { Sparkles, Linkedin, Twitter, Github, Youtube, ShieldCheck } from "lucide-react";
import "./marketing.css";

export function MarketingFooter() {
  return (
    <footer className="mkt-footer">
      <div className="mkt-footer-inner">
        {/* Brand & Mission */}
        <div className="mkt-footer-brand">
          <Link to="/" className="mkt-nav-brand">
            <div className="mkt-nav-brand-icon">
              <Sparkles size={20} color="#ffffff" />
            </div>
            <span>HireAI</span>
          </Link>
          <p>
            Autonomous technical and HR interview platform powered by live AI. Intelligent resume screening, real-time speech evaluation, and full pipeline management.
          </p>

          <div className="mkt-footer-badges">
            <span className="mkt-compliance-badge">🛡️ SOC-2 Ready</span>
            <span className="mkt-compliance-badge">🔒 GDPR Compliant</span>
            <span className="mkt-compliance-badge">⚡ 99.9% Uptime</span>
          </div>
        </div>

        {/* Product Column */}
        <div className="mkt-footer-col">
          <h4>Platform</h4>
          <Link to="/features">AI Resume Screening</Link>
          <Link to="/features">Live Voice AI Interviews</Link>
          <Link to="/features">Hiring Pipeline</Link>
          <Link to="/features">Anti-Cheat Proctoring</Link>
          <Link to="/features">RBAC &amp; Seat Management</Link>
        </div>

        {/* Solutions Column */}
        <div className="mkt-footer-col">
          <h4>Solutions</h4>
          <Link to="/book-a-demo?solution=hr">For HR Teams</Link>
          <Link to="/book-a-demo?solution=engineering">For Tech Leaders</Link>
          <Link to="/book-a-demo?solution=startup">For Startups</Link>
          <Link to="/pricing">Pricing &amp; Plans</Link>
        </div>

        {/* Resources & Company Column */}
        <div className="mkt-footer-col">
          <h4>Resources</h4>
          <Link to="/book-a-demo">Book a Demo</Link>
          <Link to="/#faq">Platform FAQ</Link>
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms &amp; Conditions</Link>
        </div>
      </div>

      <div className="mkt-footer-bottom">
        <div>
          &copy; {new Date().getFullYear()} HireAI Platform Inc - Silveri Consulting Services Pvt Ltd. All rights reserved.
        </div>

        <div className="mkt-footer-legal">
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms">Terms &amp; Conditions</Link>
        </div>

        <div className="mkt-footer-social">
          <a href="#" aria-label="LinkedIn" onClick={(e) => e.preventDefault()}>
            <Linkedin size={18} />
          </a>
          <a href="#" aria-label="Twitter" onClick={(e) => e.preventDefault()}>
            <Twitter size={18} />
          </a>
          <a href="#" aria-label="GitHub" onClick={(e) => e.preventDefault()}>
            <Github size={18} />
          </a>
          <a href="#" aria-label="YouTube" onClick={(e) => e.preventDefault()}>
            <Youtube size={18} />
          </a>
        </div>
      </div>
    </footer>
  );
}
