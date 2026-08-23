import { useState, useEffect, useRef, useCallback } from "react";

const GRACE_PERIOD_MS = 10000;
const VIOLATION_COOLDOWN_MS = 3000;
const DISMISS_COOLDOWN_MS = 2000;

/**
 * Client-side browser proctoring for live interviews.
 *
 * Monitors (2-strike system):
 *  - Tab switch / minimization  → Page Visibility API (`visibilitychange`)
 *  - Window focus loss / Alt+Tab → `window.blur`
 *  - Exiting fullscreen mode    → Fullscreen API (`fullscreenchange`)
 *
 * Strike 1 shows a warning modal; Strike 2 fires `onAutoSubmit`.
 */
const useProctoring = ({ enabled = true, assessmentStarted = false, onAutoSubmit }) => {
  const [warningStage, setWarningStage] = useState("idle"); // "idle" | "warned" | "submitted"
  const [activeWarning, setActiveWarning] = useState(null); // { type, message }
  const [isFullscreen, setIsFullscreen] = useState(false);

  const warningStageRef = useRef("idle");
  const enabledRef = useRef(enabled);
  const assessmentStartedRef = useRef(assessmentStarted);
  const onAutoSubmitRef = useRef(onAutoSubmit);
  const cooldownUntilRef = useRef(0);
  const monitoringActiveRef = useRef(false);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  useEffect(() => {
    assessmentStartedRef.current = assessmentStarted;
  }, [assessmentStarted]);

  useEffect(() => {
    onAutoSubmitRef.current = onAutoSubmit;
  }, [onAutoSubmit]);

  const requestFullscreen = useCallback(async () => {
    try {
      const elem = document.documentElement;
      if (elem.requestFullscreen) {
        await elem.requestFullscreen();
      } else if (elem.webkitRequestFullscreen) {
        await elem.webkitRequestFullscreen();
      }
      setIsFullscreen(true);
    } catch (err) {
      console.warn("Proctoring: Fullscreen request failed:", err.message);
    }
  }, []);

  // Central violation handler — enforces the 2-strike policy.
  const handleViolation = useCallback((type, message) => {
    if (!enabledRef.current || !assessmentStartedRef.current) return;
    if (!monitoringActiveRef.current) return; // Still inside the startup grace period

    const now = Date.now();
    if (now < cooldownUntilRef.current) return; // Anti-collision cooldown (dual-event firing)

    const stage = warningStageRef.current;

    if (stage === "idle") {
      // Strike 1 → pause behind warning modal
      warningStageRef.current = "warned";
      cooldownUntilRef.current = now + VIOLATION_COOLDOWN_MS;
      setWarningStage("warned");
      setActiveWarning({ type, message });
    } else if (stage === "warned") {
      // Strike 2 → auto-submit immediately
      warningStageRef.current = "submitted";
      setWarningStage("submitted");
      setActiveWarning(null);
      if (typeof onAutoSubmitRef.current === "function") {
        onAutoSubmitRef.current();
      }
    }
  }, []);

  // Dismiss warning and re-enter fullscreen (called from a user click, so the
  // browser allows the fullscreen request).
  const dismissWarning = useCallback(() => {
    setActiveWarning(null);
    cooldownUntilRef.current = Date.now() + DISMISS_COOLDOWN_MS;
    requestFullscreen();
  }, [requestFullscreen]);

  // On start: enter fullscreen, then hold violations during a grace period so
  // page/asset rendering cannot trigger false positives.
  useEffect(() => {
    if (!enabled || !assessmentStarted) return;

    monitoringActiveRef.current = false;
    requestFullscreen();

    const graceTimer = setTimeout(() => {
      monitoringActiveRef.current = true;
    }, GRACE_PERIOD_MS);

    return () => clearTimeout(graceTimer);
  }, [enabled, assessmentStarted, requestFullscreen]);

  // Browser event listeners
  useEffect(() => {
    if (!enabled) return;

    const onFullscreenChange = () => {
      const isFull = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
      setIsFullscreen(isFull);

      if (!isFull && assessmentStartedRef.current) {
        handleViolation(
          "fullscreen_exit",
          "You exited fullscreen mode. Please remain in fullscreen during the assessment."
        );
      }
    };

    const onVisibilityChange = () => {
      if (document.hidden && assessmentStartedRef.current) {
        handleViolation(
          "tab_switch",
          "You switched away from the assessment tab. Please stay on the test page."
        );
      }
    };

    const onWindowBlur = () => {
      if (assessmentStartedRef.current) {
        handleViolation(
          "window_blur",
          "You moved away from the assessment window. Please keep focus on the assessment."
        );
      }
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("webkitfullscreenchange", onFullscreenChange);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onWindowBlur);

    return () => {
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("webkitfullscreenchange", onFullscreenChange);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onWindowBlur);
    };
  }, [enabled, handleViolation]);

  return {
    warningStage,
    activeWarning,
    isFullscreen,
    requestFullscreen,
    dismissWarning,
  };
};

export default useProctoring;
