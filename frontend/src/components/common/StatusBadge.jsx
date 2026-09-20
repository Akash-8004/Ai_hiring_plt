import React from "react";
import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";

const ICONS = { shortlisted: CheckCircle2, rejected: XCircle, invited: Clock, unparseable: AlertTriangle };

export function StatusBadge({ status, cls, label }) {
  const key = cls || (status === "Shortlisted" ? "shortlisted" : "rejected");
  const Icon = ICONS[key] || CheckCircle2;
  return (
    <span className={`status-badge ${key}`}>
      <Icon size={15} />
      {label || status}
    </span>
  );
}