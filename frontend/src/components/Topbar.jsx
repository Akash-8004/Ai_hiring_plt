import React from "react";
import { Loader2, PanelLeft, UsersRound, XCircle } from "lucide-react";

export function Topbar({ title, company, busy, onLoadSamples, onClear }) {
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">{company?.role || "Company Admin"}</div>
        <h1>{title}</h1>
      </div>
      <div className="topbar-actions">
        <button className="icon-button" title="Collapse sidebar"><PanelLeft size={18} /></button>
        <button className="secondary-button" onClick={onLoadSamples} disabled={busy}>
          {busy ? <Loader2 className="spin" size={17} /> : <UsersRound size={17} />}
          Samples
        </button>
        <button className="secondary-button danger" onClick={onClear} disabled={busy}>
          <XCircle size={17} />
          Clear
        </button>
      </div>
    </header>
  );
}
