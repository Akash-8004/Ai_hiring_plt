import React, { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Sparkles, Menu, X, ChevronDown, ArrowRight,
  FileSearch, Mic, GitBranch, Shield, Users,
  Building2, Rocket, Landmark, GraduationCap, Briefcase,
  BookOpen, BarChart3, HelpCircle, LayoutGrid, CheckCircle2,
} from "lucide-react";
import "./marketing.css";

const PRODUCT_ITEMS = [
  {
    to: "/features",
    icon: FileSearch,
    title: "AI Resume Screening",
    badge: "Smart Match",
    desc: "Parse PDF/DOCX resumes and score candidates with custom AI criteria.",
    theme: "blue",
  },
  {
    to: "/features",
    icon: Mic,
    title: "Live Voice AI Interviews",
    badge: "Live AI",
    desc: "Autonomous HR and technical rounds with real-time speech transcription.",
    theme: "teal",
  },
  {
    to: "/features",
    icon: GitBranch,
    title: "Hiring Pipeline & Kanban",
    desc: "Visual candidate tracking from resume intake to scorecards and offer.",
    theme: "purple",
  },
  {
    to: "/features",
    icon: Shield,
    title: "Proctoring & RBAC Security",
    desc: "Tab-switch detection, multi-tenant isolation, and complete audit trails.",
    theme: "blue",
  },
];

const SOLUTION_ITEMS = [
  {
    to: "/book-a-demo?solution=hr",
    icon: Building2,
    title: "For HR & Talent Teams",
    desc: "Eliminate manual screening and run structured candidate assessments.",
    theme: "blue",
  },
  {
    to: "/book-a-demo?solution=engineering",
    icon: Rocket,
    title: "For Tech Leaders & CTOs",
    desc: "Save engineering bandwidth with AI-driven technical vetting.",
    theme: "teal",
  },
  {
    to: "/book-a-demo?solution=startup",
    icon: Briefcase,
    title: "For Fast-Growing Startups",
    desc: "Deploy a scalable, high-speed hiring engine with minimal effort.",
    theme: "purple",
  },
  {
    to: "/book-a-demo?solution=campus",
    icon: GraduationCap,
    title: "For University Campus Drives",
    desc: "Screen thousands of graduate applicants consistently at volume.",
    theme: "teal",
  },
];

const RESOURCE_ITEMS = [
  { to: "/features", icon: BarChart3, title: "Platform Features", desc: "Detailed breakdown of all platform capabilities" },
  { to: "/pricing", icon: LayoutGrid, title: "Pricing & Plans", desc: "Transparent starter, growth & enterprise pricing" },
  { to: "/book-a-demo", icon: HelpCircle, title: "Schedule Live Demo", desc: "Get a personalized 30-min platform walkthrough" },
  { to: "/#faq", icon: BookOpen, title: "FAQ & Knowledge Base", desc: "Common questions about voice AI and integrations" },
];

export function MarketingNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeDropdown, setActiveDropdown] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (navRef.current && !navRef.current.contains(e.target)) {
        setActiveDropdown(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close dropdown and mobile menu on route changes
  useEffect(() => {
    setActiveDropdown(null);
    setMobileOpen(false);
  }, [location.pathname, location.hash]);

  const handleDropdownToggle = (key) => {
    setActiveDropdown((current) => (current === key ? null : key));
  };

  const handleItemClick = (item) => {
    setActiveDropdown(null);
    setMobileOpen(false);
    if (item.to) {
      if (item.to.startsWith("/#")) {
        const anchor = item.to.replace("/#", "");
        if (location.pathname === "/") {
          document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
        } else {
          navigate(`/#${anchor}`);
        }
      } else {
        navigate(item.to);
      }
    }
  };

  const goAnchor = (anchor) => {
    setActiveDropdown(null);
    setMobileOpen(false);
    if (location.pathname === "/") {
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
    } else {
      navigate(`/#${anchor}`);
    }
  };

  const isActive = (path) => location.pathname === path;

  return (
    <nav className="mkt-nav" ref={navRef}>
      <Link to="/" className="mkt-nav-brand">
        <div className="mkt-nav-brand-icon">
          <Sparkles size={20} color="#ffffff" />
        </div>
        <span>HireAI</span>
        <span className="mkt-nav-brand-badge">SaaS</span>
      </Link>

      <div className="mkt-nav-center">
        <button
          className={`mkt-nav-link ${location.pathname === "/" && location.hash === "#why" ? "active" : ""}`}
          onClick={() => goAnchor("why")}
        >
          Why HireAI?
        </button>

        {/* Products Mega Dropdown */}
        <div
          className={`mkt-nav-item ${activeDropdown === "products" ? "open" : ""}`}
          onMouseEnter={() => setActiveDropdown("products")}
          onMouseLeave={() => setActiveDropdown(null)}
        >
          <button
            className="mkt-nav-link"
            onClick={() => handleDropdownToggle("products")}
            aria-expanded={activeDropdown === "products"}
          >
            Products <ChevronDown size={14} className="chev" />
          </button>
          <div className="mkt-mega-dropdown mkt-mega-products">
            <div className="mkt-mega-col-main">
              {PRODUCT_ITEMS.map((item) => (
                <button
                  key={item.title}
                  className={`mkt-dropdown-item ${item.theme || ""}`}
                  onClick={() => handleItemClick(item)}
                >
                  <span className="di-icon"><item.icon size={18} /></span>
                  <span className="di-text">
                    <span className="di-header">
                      <strong>{item.title}</strong>
                      {item.badge && <span className="di-badge">{item.badge}</span>}
                    </span>
                    <span>{item.desc}</span>
                  </span>
                </button>
              ))}
            </div>
            <div className="mkt-mega-col-side">
              <div className="mkt-spotlight-card">
                <h5><Sparkles size={14} /> Live AI Demo</h5>
                <p>Experience human-like voice interview simulation with dynamic coding challenges.</p>
                <Link to="/book-a-demo" className="mkt-spotlight-link" onClick={() => setActiveDropdown(null)}>
                  Book a live walkthrough <ArrowRight size={13} />
                </Link>
              </div>
              <div style={{ marginTop: "1rem", fontSize: "0.75rem", color: "var(--mkt-muted-dim)" }}>
                ⚡ 99.9% uptime &middot; Multi-tenant RBAC ready
              </div>
            </div>
          </div>
        </div>

        {/* Solutions Mega Dropdown */}
        <div
          className={`mkt-nav-item ${activeDropdown === "solutions" ? "open" : ""}`}
          onMouseEnter={() => setActiveDropdown("solutions")}
          onMouseLeave={() => setActiveDropdown(null)}
        >
          <button
            className="mkt-nav-link"
            onClick={() => handleDropdownToggle("solutions")}
            aria-expanded={activeDropdown === "solutions"}
          >
            Solutions <ChevronDown size={14} className="chev" />
          </button>
          <div className="mkt-mega-dropdown mkt-mega-solutions">
            {SOLUTION_ITEMS.map((item) => (
              <button
                key={item.title}
                className={`mkt-dropdown-item ${item.theme || ""}`}
                onClick={() => handleItemClick(item)}
              >
                <span className="di-icon"><item.icon size={18} /></span>
                <span className="di-text">
                  <strong>{item.title}</strong>
                  <span>{item.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <Link
          to="/pricing"
          className={`mkt-nav-link ${isActive("/pricing") ? "active" : ""}`}
        >
          Pricing
        </Link>

        {/* Resources Dropdown */}
        <div
          className={`mkt-nav-item ${activeDropdown === "resources" ? "open" : ""}`}
          onMouseEnter={() => setActiveDropdown("resources")}
          onMouseLeave={() => setActiveDropdown(null)}
        >
          <button
            className="mkt-nav-link"
            onClick={() => handleDropdownToggle("resources")}
            aria-expanded={activeDropdown === "resources"}
          >
            Resources <ChevronDown size={14} className="chev" />
          </button>
          <div className="mkt-mega-dropdown mkt-mega-resources">
            {RESOURCE_ITEMS.map((item) => (
              <button
                key={item.title}
                className="mkt-dropdown-item"
                onClick={() => handleItemClick(item)}
              >
                <span className="di-icon"><item.icon size={18} /></span>
                <span className="di-text">
                  <strong>{item.title}</strong>
                  <span>{item.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <Link
          to="/book-a-demo"
          className={`mkt-nav-link ${isActive("/book-a-demo") ? "active" : ""}`}
        >
          Contact us
        </Link>
      </div>

      <div className="mkt-nav-right">
        <Link
          to="/login"
          className={`mkt-btn mkt-btn-secondary ${isActive("/login") ? "active" : ""}`}
        >
          Login
        </Link>
        <Link
          to="/book-a-demo"
          className="mkt-btn mkt-btn-primary mkt-nav-cta-desktop"
        >
          Book a demo <ArrowRight size={15} />
        </Link>
        <button
          className="mkt-mobile-toggle"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle navigation menu"
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="mkt-mobile-menu">
          <button className="mkt-nav-link" onClick={() => goAnchor("why")}>Why HireAI?</button>
          <Link to="/features" className="mkt-nav-link" onClick={() => setMobileOpen(false)}>All Features</Link>
          <Link to="/pricing" className="mkt-nav-link" onClick={() => setMobileOpen(false)}>Pricing Plans</Link>
          <Link to="/book-a-demo" className="mkt-nav-link" onClick={() => setMobileOpen(false)}>Book a Demo</Link>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--mkt-border)" }}>
            <Link to="/login" className="mkt-btn mkt-btn-secondary" onClick={() => setMobileOpen(false)}>Login</Link>
            <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary" onClick={() => setMobileOpen(false)}>Book a Demo</Link>
          </div>
        </div>
      )}
    </nav>
  );
}
