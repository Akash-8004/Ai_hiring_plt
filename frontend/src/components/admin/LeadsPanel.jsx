import React, { useEffect, useState } from "react";
import {
  Mail, Building2, Phone, User, Calendar, MessageSquare,
  CheckCircle2, XCircle, Eye, UserPlus, RefreshCw,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "converted", label: "Converted" },
  { value: "closed", label: "Closed" },
];

function statusBadgeClass(status) {
  return {
    new: "badge-info",
    contacted: "badge-warning",
    converted: "badge-success",
    closed: "badge-muted",
  }[status] || "badge-muted";
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function LeadsPanel({ onConvertLead, onRefresh }) {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState("");
  const [updating, setUpdating] = useState(false);

  const loadLeads = async () => {
    setLoading(true);
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const data = await apiFetchJson(`/api/admin/leads${qs}`);
      setLeads(data.leads || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const openDetail = async (leadId) => {
    setSelectedId(leadId);
    try {
      const data = await apiFetchJson(`/api/admin/leads/${leadId}`);
      setDetail(data);
    } catch {
      setDetail(null);
    }
  };

  const updateStatus = async (status) => {
    if (!selectedId) return;
    setUpdating(true);
    try {
      const body = { status };
      if (note.trim()) body.note = note.trim();
      const data = await apiFetchJson(`/api/admin/leads/${selectedId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setDetail(data.lead);
      setNote("");
      await loadLeads();
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(err.message || "Failed to update lead.");
    } finally {
      setUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedId || !window.confirm("Delete this lead permanently?")) return;
    try {
      await apiFetchJson(`/api/admin/leads/${selectedId}`, { method: "DELETE" });
      setSelectedId(null);
      setDetail(null);
      await loadLeads();
      if (onRefresh) onRefresh();
    } catch (err) {
      alert(err.message || "Failed to delete lead.");
    }
  };

  return (
    <div className="admin-tab-content">
      <div className="admin-section-header">
        <div>
          <h2 className="section-title">Demo Leads</h2>
          <p className="text-muted text-sm">{total} total lead{total !== 1 ? "s" : ""}</p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            className="input-field input-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={loadLeads}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      <div className="leads-layout">
        <div className="leads-table-wrap">
          {loading ? (
            <p className="text-muted p-4">Loading leads…</p>
          ) : leads.length === 0 ? (
            <p className="text-muted p-4">No leads found.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Contact</th>
                  <th>Email</th>
                  <th>Submitted</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead._id} className={selectedId === lead._id ? "row-selected" : ""}>
                    <td>{lead.company_name}</td>
                    <td>{lead.contact_name}</td>
                    <td>{lead.work_email}</td>
                    <td>{formatDate(lead.created_at)}</td>
                    <td>
                      <span className={`badge ${statusBadgeClass(lead.status)}`}>
                        {lead.status}
                      </span>
                    </td>
                    <td>
                      <button className="btn btn-secondary btn-sm" onClick={() => openDetail(lead._id)}>
                        <Eye size={14} /> View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {detail && (
          <div className="leads-detail-panel">
            <h3 className="section-subtitle">{detail.company_name}</h3>
            <div className="lead-detail-grid">
              <div className="lead-detail-row"><User size={14} /><span>{detail.contact_name}</span></div>
              <div className="lead-detail-row"><Mail size={14} /><span>{detail.work_email}</span></div>
              {detail.phone && <div className="lead-detail-row"><Phone size={14} /><span>{detail.phone}</span></div>}
              {detail.industry && <div className="lead-detail-row"><Building2 size={14} /><span>{detail.industry}</span></div>}
              {detail.team_size && <div className="lead-detail-row"><User size={14} /><span>Team: {detail.team_size}</span></div>}
              {detail.hiring_volume && <div className="lead-detail-row"><Calendar size={14} /><span>{detail.hiring_volume}</span></div>}
              <div className="lead-detail-row">
                <span className={`badge ${statusBadgeClass(detail.status)}`}>{detail.status}</span>
              </div>
            </div>
            {detail.message && (
              <div className="lead-message-box">
                <MessageSquare size={14} />
                <p>{detail.message}</p>
              </div>
            )}
            {(detail.notes || []).length > 0 && (
              <div className="lead-notes">
                <h4>Notes</h4>
                {detail.notes.map((n, i) => (
                  <div key={i} className="lead-note-item">
                    <span className="text-muted text-sm">{n.by} · {formatDate(n.at)}</span>
                    <p>{n.text}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="form-group mt-4">
              <label className="form-label">Add note (optional)</label>
              <textarea className="input-field" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <div className="lead-actions">
              {detail.status === "new" && (
                <button className="btn btn-secondary btn-sm" disabled={updating} onClick={() => updateStatus("contacted")}>
                  <CheckCircle2 size={14} /> Mark contacted
                </button>
              )}
              {detail.status !== "converted" && detail.status !== "closed" && (
                <>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => onConvertLead(detail)}
                  >
                    <UserPlus size={14} /> Onboard
                  </button>
                  <button className="btn btn-secondary btn-sm" disabled={updating} onClick={() => updateStatus("closed")}>
                    <XCircle size={14} /> Close
                  </button>
                </>
              )}
              <button className="btn btn-danger btn-sm" onClick={handleDelete}>Delete</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
