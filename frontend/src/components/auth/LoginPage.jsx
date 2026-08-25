import React, { useState } from "react";
import { Lock, Mail, Eye, EyeOff, ShieldCheck, Sparkles, Building2 } from "lucide-react";
import { useAuth } from "../../hooks/useAuth";

export function LoginPage() {
  const { login, sessionError, setSessionError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Please enter both email and password.");
      return;
    }

    setError("");
    if (setSessionError) setSessionError("");
    setLoading(true);

    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err.message || "Failed to sign in. Please verify your credentials.");
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
          <h1 className="login-title">AI Hiring Platform</h1>
          <p className="login-subtitle">
            Autonomous Talent Intelligence & Voice Interview Platform
          </p>
        </div>

        {sessionError ? (
          <div className="login-alert warning">
            <span>{sessionError}</span>
          </div>
        ) : null}

        {error ? (
          <div className="login-alert error">
            <span>{error}</span>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label className="form-label" htmlFor="email-input">
              Work Email
            </label>
            <div className="input-with-icon">
              <Mail size={18} className="input-icon" />
              <input
                id="email-input"
                type="email"
                className="input-field"
                placeholder="admin@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                disabled={loading}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password-input">
              Password
            </label>
            <div className="input-with-icon">
              <Lock size={18} className="input-icon" />
              <input
                id="password-input"
                type={showPassword ? "text" : "password"}
                className="input-field"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary login-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="flex-center gap-2">
                <span className="spinner-small" /> Signing in...
              </span>
            ) : (
              "Sign In to Workspace"
            )}
          </button>
        </form>

        <div className="login-footer">
          <div className="login-security-tag">
            <ShieldCheck size={14} /> Multi-Tenant Role Isolation & Enterprise Security
          </div>
          <p className="login-help-text">
            Need workspace access? Contact your organization administrator or platform Super Admin.
          </p>
        </div>
      </div>
    </div>
  );
}
