import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Lock, Eye, EyeOff, KeyRound, ShieldCheck, Sparkles, AlertTriangle } from "lucide-react";
import { apiFetchJson } from "../../utils/api";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [passwordError, setPasswordError] = useState("");

  const validatePassword = () => {
    const missing = [];
    if (password.length < 8) missing.push("at least 8 characters");
    if (!/[A-Z]/.test(password)) missing.push("an uppercase letter");
    if (!/[a-z]/.test(password)) missing.push("a lowercase letter");
    if (!/\d/.test(password)) missing.push("a digit");
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) missing.push("a special character");
    if (missing.length) {
      setPasswordError(`Password must include ${missing.join(", ")}.`);
      return false;
    }
    if (password !== confirmPassword) {
      setPasswordError("Passwords do not match.");
      return false;
    }
    setPasswordError("");
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!validatePassword()) return;

    setLoading(true);
    try {
      await apiFetchJson("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      navigate("/login?reset=success", { replace: true });
    } catch (err) {
      setError(err.message || "Failed to reset password. The link may have expired.");
    } finally {
      setLoading(false);
    }
  };

  // No token in the URL at all — the user opened the page directly.
  if (!token) {
    return (
      <div className="login-screen">
        <div className="login-background-glow" />
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo-badge">
              <Sparkles size={24} className="icon-pulse" />
            </div>
            <h1 className="login-title">Silveri Hire</h1>
            <p className="login-subtitle">Invalid reset link</p>
          </div>
          <div className="login-alert error">
            <span>
              <AlertTriangle size={14} /> This reset link is incomplete. Please
              use the full link from your email, or request a new one.
            </span>
          </div>
          <div className="login-footer">
            <p className="login-help-text">
              <Link to="/forgot-password" className="auth-link">
                Request a new reset link
              </Link>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-screen">
      <div className="login-background-glow" />
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-badge">
            <Sparkles size={24} className="icon-pulse" />
          </div>
          <h1 className="login-title">Silveri Hire</h1>
          <p className="login-subtitle">Set a new password</p>
        </div>

        {error ? (
          <div className="login-alert error">
            <span>{error}</span>
            <p className="mt-2">
              <Link to="/forgot-password" className="auth-link">
                Request a new reset link
              </Link>
            </p>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label className="form-label" htmlFor="new-password-input">
              New Password
            </label>
            <div className="input-with-icon">
              <Lock size={18} className="input-icon" />
              <input
                id="new-password-input"
                type={showPassword ? "text" : "password"}
                className="input-field font-mono"
                placeholder="Minimum 8 characters (e.g. Employee@123)"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (passwordError) setPasswordError("");
                }}
                minLength={8}
                autoComplete="new-password"
                disabled={loading}
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="confirm-password-input">
              Confirm New Password
            </label>
            <div className="input-with-icon">
              <KeyRound size={18} className="input-icon" />
              <input
                id="confirm-password-input"
                type={showPassword ? "text" : "password"}
                className="input-field font-mono"
                placeholder="Re-enter your new password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  if (passwordError) setPasswordError("");
                }}
                minLength={8}
                autoComplete="new-password"
                disabled={loading}
                required
              />
            </div>
            {passwordError ? <span className="field-error">{passwordError}</span> : null}
            <span className="form-hint">
              Must be at least 8 chars with uppercase, lowercase, number &amp; symbol.
              This link can only be used once.
            </span>
          </div>

          <button
            type="submit"
            className="btn btn-primary login-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="flex-center gap-2">
                <span className="spinner-small" /> Resetting...
              </span>
            ) : (
              "Reset Password"
            )}
          </button>
        </form>

        <div className="login-footer">
          <div className="login-security-tag">
            <ShieldCheck size={14} /> Multi-Tenant Role Isolation & Enterprise Security
          </div>
          <p className="login-help-text">
            <Link to="/login" className="auth-link">
              Back to Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
