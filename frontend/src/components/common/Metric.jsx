import React from "react";

export function Metric({ icon: Icon, label, value, tone = "blue" }) {
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-icon"><Icon size={19} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
