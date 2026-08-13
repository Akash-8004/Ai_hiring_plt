import React, { useState } from "react";
import { CheckCircle2, Copy } from "lucide-react";

export function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button className="icon-button" onClick={copy} title={copied ? "Copied" : "Copy link"}>
      {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
    </button>
  );
}
