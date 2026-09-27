import React, { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Sparkles, Menu, X, ChevronDown, ArrowRight,
  FileSearch, Mic, GitBranch, Shield,
} from "lucide-react";
import "./marketing.css";

const PRODUCT_ITEMS = [
  {
    to: "/features",
    icon: FileSearch,
    title: "AI Resume Screening",
    desc: "Parse PDF/DOCX resumes and score candidates with custom AI criteria.",
    theme: "blue",
  },
  {
    to: "/features",
    icon: Mic,
    title: "Live Voice AI Interviews",
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

  // Lock body & document scroll when mobile menu is open to prevent background scrolling
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
      document.documentElement.style.overflow = "hidden";
      document.body.style.touchAction = "none";
    } else {
      document.body.style.overflow = "";
      document.documentElement.style.overflow = "";
      document.body.style.touchAction = "";
    }
    return () => {
      document.body.style.overflow = "";
      document.documentElement.style.overflow = "";
      document.body.style.touchAction = "";
    };
  }, [mobileOpen]);

  // Close mobile drawer if resized to desktop
  useEffect(() => {
    function handleResize() {
      if (window.innerWidth > 1080) {
        setMobileOpen(false);
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const isActive = (path) => location.pathname === path;

  return (
    <>
      <nav className="mkt-nav" ref={navRef}>
        <Link to="/" className="mkt-nav-brand" onClick={() => setMobileOpen(false)}>
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

          <Link
            to="/pricing"
            className={`mkt-nav-link ${isActive("/pricing") ? "active" : ""}`}
          >
            Pricing
          </Link>

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
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </nav>

      {mobileOpen && (
        <div className="mkt-mobile-menu">
          <div className="mkt-mobile-nav-group">
            <span className="mkt-mobile-group-title">Navigation</span>
            <button className="mkt-mobile-link" onClick={() => goAnchor("why")}>
              Why HireAI?
            </button>
            <Link to="/features" className="mkt-mobile-link" onClick={() => setMobileOpen(false)}>
              All Features & Capabilities
            </Link>
            <Link to="/pricing" className="mkt-mobile-link" onClick={() => setMobileOpen(false)}>
              Pricing & Plans
            </Link>
            <Link to="/book-a-demo" className="mkt-mobile-link" onClick={() => setMobileOpen(false)}>
              Contact & Book Demo
            </Link>
          </div>

          <div className="mkt-mobile-nav-group">
            <span className="mkt-mobile-group-title">Core Products</span>
            {PRODUCT_ITEMS.map((item) => (
              <button
                key={item.title}
                className="mkt-mobile-product-link"
                onClick={() => handleItemClick(item)}
              >
                <span className="mkt-mobile-product-icon"><item.icon size={16} /></span>
                <span>{item.title}</span>
              </button>
            ))}
          </div>

          <div className="mkt-mobile-auth-actions">
            <Link to="/login" className="mkt-btn mkt-btn-secondary full-w" onClick={() => setMobileOpen(false)}>
              Sign in to Portal
            </Link>
            <Link to="/book-a-demo" className="mkt-btn mkt-btn-primary full-w" onClick={() => setMobileOpen(false)}>
              Book a Demo <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      )}
    </>
  );
}
