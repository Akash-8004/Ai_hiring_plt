import React, { useState } from "react";
import { FileText, Info, Loader2, Sparkles, Upload } from "lucide-react";
import { Field } from "../common/Field";
import { ALLOWED_RESUME_ACCEPT } from "../../constants";
import { UploadProgress } from "./UploadProgress";

export function ResumeIntake({ onManualResume, onUpload, saving, uploadBatch, onDismissBatch, pollError }) {
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
          <span className="upload-accepted-formats">Supported formats: PDF (Text/Scanned), DOCX, TXT, PNG, JPG, JPEG</span>
          <div className="upload-notice">
            <Sparkles size={14} />
            <span>Scanned / image-only PDFs and resume images (PNG/JPG) are automatically transcribed with Gemini Vision OCR.</span>
          </div>
          <input
            type="file"
            multiple
            accept={ALLOWED_RESUME_ACCEPT}
            onChange={(event) => onUpload(event.target.files)}
            disabled={saving}
          />
        </div>

        {uploadBatch ? (
          <UploadProgress batch={uploadBatch} onDismiss={onDismissBatch} pollError={pollError} />
        ) : null}
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
