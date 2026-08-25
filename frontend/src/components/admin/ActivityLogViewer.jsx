import React, { useEffect, useState } from "react";
import {
  Search,
  Filter,
  RefreshCw,
  Download,
  AlertTriangle,
  Info,
  AlertOctagon,
  ChevronDown,
  ChevronRight,
  Clock,
  User,
  Building2,
  Database,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";

export function ActivityLogViewer({ initialCompanyId = null, companies = [] }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Filters
  const [companyFilter, setCompanyFilter] = useState(initialCompanyId || "");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedLogId, setExpandedLogId] = useState(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.append("page", page.toString());
      params.append("limit", limit.toString());
      if (companyFilter) params.append("company_id", companyFilter);
      if (categoryFilter) params.append("category", categoryFilter);
      if (severityFilter) params.append("severity", severityFilter);
      if (searchQuery.trim()) params.append("search", searchQuery.trim());

      const data = await apiFetchJson(`/api/admin/audit-log?${params.toString()}`);
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [page, companyFilter, categoryFilter, severityFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchLogs();
  };

  const handleExportCSV = () => {
    if (!logs.length) return;
    const headers = ["Timestamp", "Action", "Category", "Severity", "Actor Email", "Actor Role", "Company", "Target", "IP Address"];
    const rows = logs.map((l) => [
      l.timestamp,
      l.action,
      l.category,
      l.severity,
      l.actor_email,
      l.actor_role,
      l.company_name || l.company_id || "-",
      l.target_label || "-",
      l.ip_address || "-",
    ]);

    const csvContent = [headers.join(","), ...rows.map((r) => r.map((cell) => `"${(cell || "").replace(/"/g, '""')}"`).join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `audit-log-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatTimestamp = (ts) => {
    if (!ts) return "-";
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return ts;
    }
  };

  const renderSeverityBadge = (severity) => {
    switch (severity) {
      case "critical":
        return (
          <span className="log-badge badge-critical">
            <AlertOctagon size={12} /> CRITICAL
          </span>
        );
      case "warning":
        return (
          <span className="log-badge badge-warning">
            <AlertTriangle size={12} /> WARNING
          </span>
        );
      default:
        return (
          <span className="log-badge badge-info">
            <Info size={12} /> INFO
          </span>
        );
    }
  };

  return (
    <div className="activity-log-container">
      <div className="log-controls-card">
        <form onSubmit={handleSearchSubmit} className="log-filters-row">
          <div className="search-input-wrap">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              className="input-field log-search-input"
              placeholder="Search actor email, action code, or target details..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="filters-group">
            <select
              className="select-field"
              value={companyFilter}
              onChange={(e) => {
                setCompanyFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Companies</option>
              {companies.map((c) => (
                <option key={c._id} value={c._id}>
                  {c.name}
                </option>
              ))}
            </select>

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
              <option value="user_mgmt">User & Company Mgmt</option>
              <option value="job">Job Management</option>
              <option value="candidate">Candidate & Resumes</option>
              <option value="interview">Interviews & Evaluations</option>
              <option value="system">System Events</option>
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

            <button type="submit" className="btn btn-secondary" title="Search">
              <Filter size={15} /> Filter
            </button>

            <button
              type="button"
              className="btn btn-secondary btn-icon"
              onClick={fetchLogs}
              title="Refresh logs"
              disabled={loading}
            >
              <RefreshCw size={15} className={loading ? "spin" : ""} />
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleExportCSV}
              disabled={!logs.length}
              title="Export filtered logs to CSV"
            >
              <Download size={15} /> Export CSV
            </button>
          </div>
        </form>
      </div>

      {error ? <div className="notice error my-3">{error}</div> : null}

      <div className="log-table-wrapper card">
        <div className="log-table-header-info">
          <span>Showing {logs.length} of {total} audit records</span>
          {loading && <span className="text-muted ml-2">(Refreshing...)</span>}
        </div>

        <table className="log-table">
          <thead>
            <tr>
              <th style={{ width: "30px" }}></th>
              <th>Timestamp</th>
              <th>Severity</th>
              <th>Action Code</th>
              <th>Actor</th>
              <th>Target / Details</th>
              <th>IP Address</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-muted">
                  No activity log records matched the current filters.
                </td>
              </tr>
            ) : (
              logs.map((log) => {
                const isExpanded = expandedLogId === log._id;
                return (
                  <React.Fragment key={log._id}>
                    <tr
                      className={`log-row ${isExpanded ? "expanded" : ""}`}
                      onClick={() => setExpandedLogId(isExpanded ? null : log._id)}
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
                          {log.category && (
                            <span className="badge category-badge">{log.category}</span>
                          )}
                        </div>
                      </td>
                      <td className="font-mono text-muted text-xs">
                        {log.ip_address || "-"}
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="log-detail-row">
                        <td colSpan={7}>
                          <div className="log-details-card">
                            <div className="detail-meta-grid">
                              <div>
                                <strong>Log ID:</strong> <span className="font-mono">{log._id}</span>
                              </div>
                              <div>
                                <strong>Actor ID:</strong> <span className="font-mono">{log.actor_id || "-"}</span>
                              </div>
                              <div>
                                <strong>Company ID:</strong> <span className="font-mono">{log.company_id || "Platform"}</span>
                              </div>
                              <div>
                                <strong>User Agent:</strong> <span className="text-xs">{log.user_agent || "-"}</span>
                              </div>
                            </div>

                            {log.metadata && Object.keys(log.metadata).length > 0 && (
                              <div className="metadata-dump">
                                <strong>Action Metadata:</strong>
                                <pre className="json-dump">
                                  {JSON.stringify(log.metadata, null, 2)}
                                </pre>
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
    </div>
  );
}
