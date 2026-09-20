import React from "react";

export function Field({ label, value, onChange, type = "text", required = false, error = "" }) {
  return (
    <label className={`field${error ? " has-error" : ""}`}>
      <span>
        {label}
        {required ? <span className="required-mark"> *</span> : null}
      </span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
      />
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}
