import React, { useState, useEffect } from "react";
import { X, Building2, User, Mail, Lock, Shield, CheckCircle, Copy, Phone, Loader2 } from "lucide-react";
import { apiFetchJson } from "../../utils/api";

export function CompanyOnboardingModal({ isOpen, onClose, onCompanyCreated, initialData, leadId, onLeadConverted }) {
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("Technology");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [plan, setPlan] = useState("starter");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    if (initialData) {
      setCompanyName(initialData.company_name || "");
      setIndustry(initialData.industry || "Technology");
      setContactEmail(initialData.contact_email || "");
      setContactPhone(initialData.contact_phone || "");
      setPlan(initialData.plan || "starter");
      setAdminName(initialData.admin_name || initialData.contact_name || "");
      setAdminEmail(initialData.admin_email || initialData.contact_email || "");
      setAdminPassword(initialData.admin_password || "");
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await apiFetchJson("/api/admin/companies", {
        method: "POST",
        body: JSON.stringify({
          company_name: companyName.trim(),
          industry: industry.trim(),
          contact_email: contactEmail.trim(),
          contact_phone: contactPhone.trim(),
          plan,
          admin_name: adminName.trim(),
          admin_email: adminEmail.trim(),
          admin_password: adminPassword,
        }),
      });

      setSuccessData({
        companyName: companyName.trim(),
        adminEmail: adminEmail.trim(),
        adminPassword: adminPassword,
        plan,
        companyId: data.company_id,
      });

      if (leadId) {
        try {
          await apiFetchJson(`/api/admin/leads/${leadId}`, {
            method: "PUT",
            body: JSON.stringify({
              status: "converted",
              converted_company_id: data.company_id,
              note: `Converted to company ${companyName.trim()}`,
            }),
          });
          if (onLeadConverted) onLeadConverted(data.company_id);
        } catch {
          // company created; lead update is best-effort
        }
      }

      if (onCompanyCreated) {
        onCompanyCreated(data);
      }
    } catch (err) {
      setError(err.message || "Failed to onboard company.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyCredentials = () => {
    if (!successData) return;
    const text = `Company: ${successData.companyName}\nAdmin Email: ${successData.adminEmail}\nTemporary Password: ${successData.adminPassword}\nLogin Portal: ${window.location.origin}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleSendCredentialsEmail = async () => {
    if (!successData) return;
    setEmailSending(true);
    setEmailSent(null);
    try {
      const res = await apiFetchJson(
        `/api/admin/companies/${successData.companyId}/send-credentials`,
        {
          method: "POST",
          body: JSON.stringify({
            admin_email: successData.adminEmail,
            admin_password: successData.adminPassword,
          }),
        }
      );
      setEmailSent(res.ok ? "sent" : "failed");
    } catch {
      setEmailSent("failed");
    } finally {
      setEmailSending(false);
    }
  };

  const handleClose = () => {
    setCompanyName("");
    setIndustry("Technology");
    setContactEmail("");
    setContactPhone("");
    setPlan("starter");
    setAdminName("");
    setAdminEmail("");
    setAdminPassword("");
    setSuccessData(null);
    setError("");
    onClose();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content modal-md">
        <div className="modal-header">
          <div className="modal-title-group">
            <Building2 size={20} className="text-primary" />
            <h2 className="modal-title">
              {successData ? "Company Onboarded Successfully" : "Onboard New Client Company"}
            </h2>
          </div>
          <button className="btn-icon" onClick={handleClose}>
            <X size={18} />
          </button>
        </div>

        {successData ? (
          <div className="modal-body success-step">
            <div className="success-banner">
              <CheckCircle size={32} className="text-success" />
              <h3>{successData.companyName} is ready!</h3>
              <p>The company and initial Company Administrator account have been created.</p>
            </div>

            <div className="credentials-box">
              <div className="credential-row">
                <span className="label">Admin Email:</span>
                <span className="value">{successData.adminEmail}</span>
              </div>
              <div className="credential-row">
                <span className="label">Password:</span>
                <span className="value font-mono">{successData.adminPassword}</span>
              </div>
              <div className="credential-row">
                <span className="label">Assigned Plan:</span>
                <span className="value badge plan-badge">{successData.plan.toUpperCase()}</span>
              </div>
            </div>

            <div className="share-instructions">
              <p>Share these credentials with the company owner. They can log in immediately from the main login page.</p>
            </div>

            <div className="modal-footer">
              <button
                className={`btn btn-secondary ${emailSent === "sent" ? "email-send-btn sent" : emailSent === "failed" ? "email-send-btn failed" : ""}`}
                onClick={handleSendCredentialsEmail}
                disabled={emailSending || emailSent === "sent"}
              >
                {emailSending ? (
                  <><Loader2 size={16} className="spin" /> Sending...</>
                ) : emailSent === "sent" ? (
                  <><CheckCircle size={16} /> Email Sent</>
                ) : emailSent === "failed" ? (
                  <><Mail size={16} /> Retry Email</>
                ) : (
                  <><Mail size={16} /> Send Credentials via Email</>
                )}
              </button>
              <button className="btn btn-secondary" onClick={handleCopyCredentials}>
                {copied ? (
                  <>
                    <CheckCircle size={16} /> Copied to Clipboard
                  </>
                ) : (
                  <>
                    <Copy size={16} /> Copy Credentials
                  </>
                )}
              </button>
              <button className="btn btn-primary" onClick={handleClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="modal-body">
              {error ? <div className="notice error mb-4">{error}</div> : null}

              <div className="form-section-title">Company Profile</div>
              <div className="form-grid-2">
                <div className="form-group">
                  <label className="form-label">Company Name *</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Acme Tech Solutions"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Industry</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Fintech, Healthcare, SaaS"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-grid-2">
                <div className="form-group">
                  <label className="form-label">Contact Email *</label>
                  <input
                    type="email"
                    className="input-field"
                    placeholder="contact@company.com"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Contact Phone</label>
                  <input
                    type="tel"
                    className="input-field"
                    placeholder="+1 555-0199"
                    value={contactPhone}
                    onChange={(e) => setContactPhone(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Subscription Tier / Plan *</label>
                <div className="plan-selector-grid">
                  <label className={`plan-card ${plan === "starter" ? "selected" : ""}`}>
                    <input
                      type="radio"
                      name="plan"
                      value="starter"
                      checked={plan === "starter"}
                      onChange={(e) => setPlan(e.target.value)}
                    />
                    <div className="plan-name">Starter</div>
                    <div className="plan-detail">Up to 5 Users · 3 Active Jobs · 500 Credits/mo</div>
                  </label>
                  <label className={`plan-card ${plan === "growth" ? "selected" : ""}`}>
                    <input
                      type="radio"
                      name="plan"
                      value="growth"
                      checked={plan === "growth"}
                      onChange={(e) => setPlan(e.target.value)}
                    />
                    <div className="plan-name">Growth</div>
                    <div className="plan-detail">Up to 15 Users · 10 Active Jobs · 2,000 Credits/mo</div>
                  </label>
                  <label className={`plan-card ${plan === "enterprise" ? "selected" : ""}`}>
                    <input
                      type="radio"
                      name="plan"
                      value="enterprise"
                      checked={plan === "enterprise"}
                      onChange={(e) => setPlan(e.target.value)}
                    />
                    <div className="plan-name">Enterprise</div>
                    <div className="plan-detail">Up to 50 Users · 50 Active Jobs · 10,000 Credits/mo</div>
                  </label>
                </div>
              </div>

              <div className="form-section-title mt-4">Company Administrator Account</div>
              <div className="form-grid-2">
                <div className="form-group">
                  <label className="form-label">Admin Full Name *</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. John Doe"
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Admin Work Email *</label>
                  <input
                    type="email"
                    className="input-field"
                    placeholder="admin@company.com"
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Initial Password *</label>
                <input
                  type="text"
                  className="input-field font-mono"
                  placeholder="Minimum 8 characters (e.g. Company@123)"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  minLength={8}
                  required
                />
                <span className="form-hint">
                  Must be at least 8 chars with uppercase, lowercase, number & symbol.
                </span>
              </div>
            </div>

            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={loading}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Creating..." : "Create Company & Account"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
