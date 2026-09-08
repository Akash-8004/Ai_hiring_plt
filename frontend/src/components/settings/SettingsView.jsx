import React from "react";
import { Settings } from "lucide-react";

export function SettingsView() {
  return (
    <section className="settings-grid">
      {[
        ["Tenant Isolation", "Company-scoped data model placeholder"],
        ["AI Provider", "AI-powered screening and interviews"],
        ["Email Provider", "SendGrid, SES, Mailgun integration slot"],
        ["Interview Modules", "AI technical and HR interview modules active"],
      ].map(([title, copy]) => (
        <div className="setting-row" key={title}>
          <div>
            <strong>{title}</strong>
            <span>{copy}</span>
          </div>
          <button className="icon-button" title={title}><Settings size={17} /></button>
        </div>
      ))}
    </section>
  );
}
