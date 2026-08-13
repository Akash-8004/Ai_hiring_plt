import React, { useState } from "react";
import { FileText, Loader2, Upload } from "lucide-react";
import { Field } from "./common/Field";

export function ResumeIntake({ onManualResume, onUpload, saving }) {
  const [fileName, setFileName] = useState("candidate_resume.txt");
  const [text, setText] = useState("");

  function submitManual(event) {
    event.preventDefault();
    onManualResume({ file_name: fileName, text });
    setText("");
  }

  return (
    <div className="intake-layout">
      <section className="upload-panel">
        <div className="upload-drop">
          <Upload size={32} />
          <strong>Bulk Resume Upload</strong>
          <span>TXT, PDF, DOCX</span>
          <input
            type="file"
            multiple
            accept=".txt,.pdf,.docx"
            onChange={(event) => onUpload(event.target.files)}
            disabled={saving}
          />
        </div>
      </section>

      <form className="form-panel" onSubmit={submitManual}>
        <h2>Manual Resume</h2>
        <Field label="File name" value={fileName} onChange={setFileName} />
        <label className="field full">
          <span>Resume text</span>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={13} />
        </label>
        <button className="primary-button submit-button" disabled={saving || !text.trim()}>
          {saving ? <Loader2 className="spin" size={17} /> : <FileText size={17} />}
          Parse Resume
        </button>
      </form>
    </div>
  );
}
