import React, { useEffect, useState } from "react";
import {
  Gauge,
  AlertTriangle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Info,
} from "lucide-react";
import { apiFetchJson } from "../../utils/api";

function formatPrice(price) {
  if (price == null) return "—";
  return `$${Number(price).toLocaleString()}/mo`;
}

function formatPeriod(period) {
  if (!period) return "";
  const [year, month] = period.split("-");
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, 1));
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
}

export function UsageView() {
  const [billing, setBilling] = useState(null);
  const [usageData, setUsageData] = useState(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(15);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [billingRes, usageRes] = await Promise.all([
        apiFetchJson("/api/company/billing"),
        apiFetchJson(`/api/company/usage?page=${page}&limit=${limit}`),
      ]);
      setBilling(billingRes);
      setUsageData(usageRes);
    } catch (err) {
      setError(err.message || "Failed to load usage data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const credits = billing?.credits || usageData?.credits || {};
  const allowance = credits.allowance || 0;
  const used = credits.used || 0;
  const remaining = credits.remaining ?? 0;
  const usedPct = allowance > 0 ? Math.min(100, (used / allowance) * 100) : 0;
  const lowBalance = allowance > 0 && remaining < allowance * 0.2;
  const exhausted = remaining <= 0;

  const total = usageData?.usage?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const entries = usageData?.usage?.entries || [];

  return (
    <div className="usage-view">
      {error ? <div className="notice error my-4">{error}</div> : null}

      {exhausted && (
        <div className="notice error my-4">
          <AlertTriangle size={18} className="inline-icon" />
          <span>
            Your interview credits are exhausted for this billing period. Contact your platform Super Admin to add credits or upgrade your plan.
          </span>
        </div>
      )}

      <div className="usage-header-grid">
        <div className="card usage-plan-card">
          <div className="card-title-group">
            <Gauge size={18} className="text-primary" />
            <h3 className="card-title">Subscription</h3>
          </div>
          {loading ? (
            <p className="text-muted text-sm mt-3">Loading…</p>
          ) : (
            <div className="usage-stat-grid mt-3">
              <div>
                <span className="usage-stat-label">Plan</span>
                <strong className="usage-stat-value">{billing?.plan?.toUpperCase() || "—"}</strong>
              </div>
              <div>
                <span className="usage-stat-label">Price</span>
                <strong className="usage-stat-value">{formatPrice(billing?.plan_price)}</strong>
              </div>
              <div>
                <span className="usage-stat-label">Seats</span>
                <strong className="usage-stat-value">
                  {billing?.current_users ?? "—"} / {billing?.max_users ?? "—"}
                </strong>
              </div>
              <div>
                <span className="usage-stat-label">Candidate Limit</span>
                <strong className="usage-stat-value">Up to {billing?.max_candidates ? billing.max_candidates.toLocaleString() : "—"}</strong>
              </div>
            </div>
          )}
        </div>

        <div className="card usage-credits-card">
          <div className="card-header-flex">
            <div className="card-title-group">
              <Gauge size={18} className="text-primary" />
              <h3 className="card-title">Interview Credits</h3>
            </div>
            <span className="text-xs text-muted">{formatPeriod(credits.period)}</span>
          </div>
          {loading ? (
            <p className="text-muted text-sm mt-3">Loading…</p>
          ) : (
            <>
              <div className="usage-stat-grid mt-3">
                <div>
                  <span className="usage-stat-label">Allowance</span>
                  <strong className="usage-stat-value">{allowance.toLocaleString()}</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Used</span>
                  <strong className="usage-stat-value">{used.toLocaleString()}</strong>
                </div>
                <div>
                  <span className="usage-stat-label">Remaining</span>
                  <strong className={`usage-stat-value ${exhausted || lowBalance ? "text-danger" : ""}`}>
                    {remaining.toLocaleString()}
                  </strong>
                </div>
              </div>
              <div className="progress-bar-bg mt-4">
                <div
                  className={`progress-bar-fill ${exhausted || lowBalance ? "progress-danger" : ""}`}
                  style={{ width: `${usedPct}%` }}
                />
              </div>
              <p className="text-xs text-muted mt-2">{used.toLocaleString()} / {allowance.toLocaleString()} credits used ({Math.round(usedPct)}%)</p>
            </>
          )}
        </div>
      </div>

      <div className="card mt-4 usage-explainer">
        <div className="card-title-group">
          <Info size={16} className="text-primary" />
          <h3 className="card-title">How credits work</h3>
        </div>
        <p className="text-sm text-muted mt-2">
          1 credit = 1 interview minute. Both HR and Technical rounds consume credits based on each job&apos;s configured duration.
          Credits reset monthly with no rollover — unused credits do not carry over to the next period.
        </p>
      </div>

      <div className="card mt-4">
        <div className="card-header-flex">
          <h3 className="card-title">Usage Log</h3>
          <button className="btn btn-secondary btn-sm" onClick={fetchAll} disabled={loading}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Refresh
          </button>
        </div>
        <div className="table-responsive mt-3">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Candidate</th>
                <th>Round</th>
                <th>Minutes</th>
                <th>Action</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted">Loading usage log…</td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted">No usage entries yet.</td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry._id || `${entry.created_at}-${entry.candidate_email}`}>
                    <td className="text-xs text-muted">
                      {entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="font-mono text-sm">{entry.candidate_email || "—"}</td>
                    <td>
                      <span className="badge badge-subtle">{entry.round_type || "—"}</span>
                    </td>
                    <td>{entry.minutes ?? 0}</td>
                    <td>
                      <span className={`badge ${entry.action === "blocked" ? "badge-critical" : "badge-subtle"}`}>
                        {entry.action}
                      </span>
                    </td>
                    <td className="text-xs text-muted">{entry.detail || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="pagination-controls mt-4">
            <button
              className="btn btn-secondary btn-sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <span className="text-sm text-muted">
              Page {page} of {totalPages} ({total} entries)
            </span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
