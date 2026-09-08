import React from "react";
import { PanelLeft } from "lucide-react";

export function Topbar({ title, company }) {
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">{company?.role || "Company Admin"}</div>
        <h1>{title}</h1>
      </div>
      <div className="topbar-actions">
        <button className="icon-button" title="Collapse sidebar"><PanelLeft size={18} /></button>
      </div>
    </header>
  );
}
