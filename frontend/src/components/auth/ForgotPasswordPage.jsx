import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Mail, ArrowLeft, Send, CheckCircle, ShieldCheck, Sparkles } from "lucide-react";
import { apiFetchJson } from "../../utils/api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }

    const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    if (!emailPattern.test(email.trim())) {
      setError("Invalid email address");
      return;
    }

    setError("");
    setLoading(true);

    try {
      await apiFetchJson("/api/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
      setSent(true);
    } catch (err) {
      if (err.status === 429) {
        setError(err.message || "Too many requests. Please wait a few minutes and try again.");
      } else {
        setError(err.message || "Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-background-glow" />
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-badge">
            <Sparkles size={24} className="icon-pulse" />
          </div>
          <h1 className="login-title">Silveri Hire</h1>
          <p className="login-subtitle">
            {sent ? "Check your inbox" : "Forgot your password?"}
          </p>
        </div>

        {error ? (
          <div className="login-alert error">
            <span>{error}</span>
          </div>
        ) : null}

        {sent ? (
          <div className="auth-success-panel">
            <div className="success-banner">
              <CheckCircle size={32} className="text-success" />
              <h3>Reset Link Sent</h3>
              <p>
                If an account exists for <strong>{email.trim()}</strong>, a
                password reset link has been sent. The link is valid for 30
                minutes.
              </p>
            </div>
            <p className="form-hint text-center">
              Didn't receive the email? Check your spam folder, or try again in
              a minute.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label className="form-label" htmlFor="forgot-email-input">
                Work Email
              </label>
              <div className="input-with-icon">
                <Mail size={18} className="input-icon" />
                <input
                  id="forgot-email-input"
                  type="email"
                  className="input-field"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (error) setError("");
                  }}
                  autoComplete="email"
                  disabled={loading}
                  required
                />
              </div>
              <span className="form-hint">
                Enter the email you use to sign in. We'll send you a one-time
                link to set a new password.
              </span>
            </div>

            <button
              type="submit"
              className="btn btn-primary login-submit-btn"
              disabled={loading}
            >
              {loading ? (
                <span className="flex-center gap-2">
                  <span className="spinner-small" /> Sending...
                </span>
              ) : (
                <>
                  <Send size={16} /> Send Reset Link
                </>
              )}
            </button>
          </form>
        )}

        <div className="login-footer">
          <div className="login-security-tag">
            <ShieldCheck size={14} /> Multi-Tenant Role Isolation & Enterprise Security
          </div>
          <p className="login-help-text">
            <Link to="/login" className="auth-link">
              <ArrowLeft size={14} /> Back to Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
