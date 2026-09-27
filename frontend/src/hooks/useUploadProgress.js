import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetchJson } from "../utils/api";

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_DURATION_MS = 10 * 60 * 1000; // 10 minutes timeout

export function useUploadProgress({ onComplete } = {}) {
  const [activeBatch, setActiveBatch] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const [pollError, setPollError] = useState(null);

  const activeBatchIdRef = useRef(null);
  const pollInFlightRef = useRef(false);
  const pollTimerRef = useRef(null);
  const startTimeRef = useRef(null);
  const consecutiveErrorsRef = useRef(0);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
    pollInFlightRef.current = false;
  }, []);

  const fetchBatchStatus = useCallback(async (batchId, signal) => {
    if (pollInFlightRef.current) return;
    pollInFlightRef.current = true;

    try {
      const data = await apiFetchJson(`/api/resumes/upload/${encodeURIComponent(batchId)}`, { signal });
      consecutiveErrorsRef.current = 0;
      setPollError(null);
      setActiveBatch(data);

      const isTerminal = data.status === "complete" || (data.jobs && data.jobs.length > 0 && data.jobs.every((j) => j.status === "done" || j.status === "failed"));

      if (isTerminal) {
        stopPolling();
        if (onCompleteRef.current) {
          onCompleteRef.current(data);
        }
        return;
      }

      // Check timeout
      if (startTimeRef.current && Date.now() - startTimeRef.current > MAX_POLL_DURATION_MS) {
        setPollError("Upload processing timed out. Resumes may still be finishing in the background.");
        stopPolling();
        return;
      }

      // Schedule next poll
      pollTimerRef.current = setTimeout(() => {
        pollInFlightRef.current = false;
        fetchBatchStatus(batchId, signal);
      }, POLL_INTERVAL_MS);
    } catch (err) {
      if (err.name === "AbortError") return;
      consecutiveErrorsRef.current += 1;
      const delay = Math.min(POLL_INTERVAL_MS * Math.pow(1.5, consecutiveErrorsRef.current), 10000);

      if (err.status === 404) {
        setPollError("Upload batch not found.");
        stopPolling();
        return;
      }

      if (consecutiveErrorsRef.current > 5) {
        setPollError(`Unable to track upload status: ${err.message}`);
      }

      pollTimerRef.current = setTimeout(() => {
        pollInFlightRef.current = false;
        fetchBatchStatus(batchId, signal);
      }, delay);
    } finally {
      pollInFlightRef.current = false;
    }
  }, [stopPolling]);

  const startTrackingBatch = useCallback((batchId) => {
    if (!batchId) return;
    stopPolling();
    activeBatchIdRef.current = batchId;
    startTimeRef.current = Date.now();
    consecutiveErrorsRef.current = 0;
    setPollError(null);
    setIsPolling(true);

    const abortController = new AbortController();
    fetchBatchStatus(batchId, abortController.signal);
  }, [fetchBatchStatus, stopPolling]);

  const clearBatch = useCallback(() => {
    stopPolling();
    activeBatchIdRef.current = null;
    setActiveBatch(null);
    setPollError(null);
  }, [stopPolling]);

  // Check active batches on mount to restore state if page refreshed during upload
  useEffect(() => {
    const abortController = new AbortController();
    async function checkActiveBatches() {
      try {
        const data = await apiFetchJson("/api/resumes/upload/active", { signal: abortController.signal });
        if (data?.batches && data.batches.length > 0) {
          const mostRecent = data.batches[0];
          if (mostRecent?.batchId && !activeBatchIdRef.current) {
            setActiveBatch(mostRecent);
            startTrackingBatch(mostRecent.batchId);
          }
        }
      } catch {
        // Silently ignore active batch check errors on load
      }
    }
    checkActiveBatches();

    return () => {
      abortController.abort();
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [startTrackingBatch]);

  return {
    activeBatch,
    isPolling,
    pollError,
    startTrackingBatch,
    clearBatch,
  };
}
