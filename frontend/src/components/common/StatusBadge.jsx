import React from "react";
import { CheckCircle2, XCircle } from "lucide-react";

export function StatusBadge({ status }) {
  const positive = status === "Shortlisted";
  return (
    <span className={positive ? "status-badge shortlisted" : "status-badge rejected"}>
      {positive ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
      {status}
    </span>
  );
}
