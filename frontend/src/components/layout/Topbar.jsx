import React from "react";
import { Menu, PanelLeft } from "lucide-react";

export function Topbar({ title, company, onMenuClick }) {
  return (
    <header className="topbar">
      <div className="topbar-head">
        <button
          type="button"
          className="icon-button topbar-menu-btn"
          onClick={onMenuClick}
          title="Open navigation menu"
        >
          <Menu size={18} />
        </button>
        <div>
          <div className="eyebrow">{company?.role || "Company Admin"}</div>
          <h1>{title}</h1>
        </div>
      </div>
      <div className="topbar-actions">
        <button className="icon-button" title="Collapse sidebar"><PanelLeft size={18} /></button>
      </div>
    </header>
  );
}