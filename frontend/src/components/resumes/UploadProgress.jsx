import React from "react";
import { AlertTriangle, CheckCircle2, FileText, Loader2, Sparkles, X, XCircle } from "lucide-react";

export function UploadProgress({ batch, onDismiss, pollError }) {
  if (!batch) return null;

  const { total = 0, done = 0, failed = 0, jobs = [], status } = batch;
  const isComplete = status === "complete" || (jobs.length > 0 && jobs.every((j) => j.status === "done" || j.status === "failed"));
  const percent = total > 0 ? Math.round(((done + failed) / total) * 100) : 0;

  return (
    <div className="upload-progress-card">
      <div className="upload-progress-header">
        <div className="upload-progress-title">
          {!isComplete ? (
            <Loader2 className="spin" size={18} />
          ) : failed > 0 && done === 0 ? (
            <XCircle size={18} className="icon-failed" />
          ) : (
            <CheckCircle2 size={18} className="icon-success" />
          )}
          <strong>
            {!isComplete
              ? `Processing Resumes (${done + failed}/${total})`
              : `Batch Complete (${done} parsed${failed > 0 ? `, ${failed} failed` : ""})`}
          </strong>
        </div>
        {onDismiss ? (
          <button type="button" className="icon-button" onClick={onDismiss} title="Dismiss">
            <X size={16} />
          </button>
        ) : null}
      </div>

      <div className="upload-progress-bar-wrap">
        <div
          className={`upload-progress-bar ${isComplete ? (failed > 0 && done === 0 ? "failed" : "complete") : ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      {pollError ? (
        <div className="upload-progress-error">
          <AlertTriangle size={14} />
          <span>{pollError}</span>
        </div>
      ) : null}

      <div className="upload-job-list">
        {jobs.map((job, idx) => {
          const isDone = job.status === "done";
          const isFailed = job.status === "failed";
          const isProcessing = job.status === "processing";

          return (
            <div key={job._id || `${job.file_name}-${idx}`} className={`upload-job-item ${job.status}`}>
              <div className="upload-job-info">
                <FileText size={15} className="job-file-icon" />
                <span className="job-file-name" title={job.file_name}>
                  {job.file_name}
                </span>
                {job.ocr_used ? (
                  <span className="ocr-badge" title="Transcribed via Gemini Vision OCR">
                    <Sparkles size={11} /> OCR
                  </span>
                ) : null}
              </div>

              <div className="upload-job-status">
                {isProcessing ? (
                  <span className="job-status-pill processing">
                    <Loader2 className="spin" size={12} />
                    {job.stage ? `${job.stage}...` : "Processing..."}
                  </span>
                ) : isDone ? (
                  <span className="job-status-pill done">
                    <CheckCircle2 size={12} />
                    {job.candidate_name || "Parsed"}
                  </span>
                ) : isFailed ? (
                  <span className="job-status-pill failed" title={job.error || "Failed"}>
                    <XCircle size={12} />
                    {job.error ? truncate(job.error, 30) : "Failed"}
                  </span>
                ) : (
                  <span className="job-status-pill queued">Queued</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function truncate(text, max) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
