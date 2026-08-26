import React, { useEffect, useState } from "react";
import {
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertOctagon,
  AlertTriangle,
  Info,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";

/**
 * Company-scoped activity log for the Team Access screen. Backed by
 * GET /api/company/audit-log, which the backend restricts to the caller's own
 * company — so a Company Admin only ever sees their own team's activity.
 */
export function CompanyActivityLog() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(15);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.append("page", String(page));
      params.append("limit", String(limit));
      if (categoryFilter) params.append("category", categoryFilter);
      if (severityFilter) params.append("severity", severityFilter);
      const data = await apiFetchJson(`/api/company/audit-log?${params.toString()}`);
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "Failed to load activity logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, categoryFilter, severityFilter]);

  const formatTimestamp = (ts) => {
    if (!ts) return "-";
    try {
      return new Date(ts).toLocaleString(undefined, {
        timeZone: "UTC",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return ts;
    }
  };

  const renderSeverityBadge = (severity) => {
    if (severity === "critical") {
      return (
        <span className="log-badge badge-critical">
          <AlertOctagon size={12} /> CRITICAL
        </span>
      );
    }
    if (severity === "warning") {
      return (
        <span className="log-badge badge-warning">
          <AlertTriangle size={12} /> WARNING
        </span>
      );
    }
    return (
      <span className="log-badge badge-info">
        <Info size={12} /> INFO
      </span>
    );
  };

  return (
    <div className="card mt-4">
      <div className="card-header-flex">
        <div className="card-title-group">
          <Activity size={18} className="text-primary" />
          <h3 className="card-title">Team Activity Logs</h3>
        </div>
        <div className="filters-group">
          <select
            className="select-field"
            value={categoryFilter}
            onChange={(e) => {
              setCategoryFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All Categories</option>
            <option value="auth">Auth & Session</option>
            <option value="user_mgmt">User Management</option>
            <option value="job">Job Management</option>
            <option value="candidate">Candidate & Resumes</option>
            <option value="interview">Interviews</option>
            <option value="system">System</option>
          </select>
          <select
            className="select-field"
            value={severityFilter}
            onChange={(e) => {
              setSeverityFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All Severities</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            onClick={fetchLogs}
            title="Refresh logs"
            disabled={loading}
          >
            <RefreshCw size={15} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      <p className="banner-subtitle mt-1">
        A record of what your team members do — logins, resume uploads, interview invites and evaluations.
      </p>

      {error ? <div className="notice error my-3">{error}</div> : null}

      <div className="table-responsive mt-3">
        <table className="log-table">
          <thead>
            <tr>
              <th style={{ width: "30px" }}></th>
              <th>Timestamp</th>
              <th>Severity</th>
              <th>Action</th>
              <th>Team Member</th>
              <th>Target / Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-muted">
                  {loading ? "Loading activity…" : "No activity recorded yet for your team."}
                </td>
              </tr>
            ) : (
              logs.map((log) => {
                const isExpanded = expandedId === log._id;
                return (
                  <React.Fragment key={log._id}>
                    <tr
                      className={`log-row ${isExpanded ? "expanded" : ""}`}
                      onClick={() => setExpandedId(isExpanded ? null : log._id)}
                    >
                      <td className="text-center">
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </td>
                      <td className="log-time text-muted font-mono whitespace-nowrap">
                        <Clock size={12} className="inline mr-1" />
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td>{renderSeverityBadge(log.severity)}</td>
                      <td>
                        <span className="log-action font-mono">{log.action}</span>
                      </td>
                      <td>
                        <div className="log-actor">
                          <span className="actor-email">{log.actor_email}</span>
                          <span className="actor-role text-muted">{log.actor_role}</span>
                        </div>
                      </td>
                      <td>
                        <div className="log-target">
                          {log.target_label ? (
                            <span className="target-label">{log.target_label}</span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                          {log.category && <span className="badge category-badge">{log.category}</span>}
                        </div>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="log-detail-row">
                        <td colSpan={6}>
                          <div className="log-details-card">
                            <div className="detail-meta-grid">
                              <div>
                                <strong>Timestamp:</strong>{" "}
                                <span className="font-mono">{log.timestamp}</span>
                              </div>
                              <div>
                                <strong>IP Address:</strong>{" "}
                                <span className="font-mono">{log.ip_address || "-"}</span>
                              </div>
                            </div>
                            {log.metadata && Object.keys(log.metadata).length > 0 && (
                              <div className="metadata-dump">
                                <strong>Details:</strong>
                                <pre className="json-dump">{JSON.stringify(log.metadata, null, 2)}</pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {total > limit && (
        <div className="log-pagination">
          <button
            className="btn btn-secondary btn-sm"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {page} of {Math.ceil(total / limit)}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            disabled={page * limit >= total || loading}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
