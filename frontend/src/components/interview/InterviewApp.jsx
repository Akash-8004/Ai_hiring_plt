import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  Info,
  Loader2,
  Mic,
  MicOff,
  Monitor,
  PhoneOff,
  UsersRound,
  Video,
  VideoOff,
  Volume2,
  XCircle,
  ShieldAlert,
} from "lucide-react";
import { createLiveClient } from "./liveClient";
import ProctoringWarningModal from "./ProctoringWarningModal";
import useProctoring from "../../hooks/useProctoring";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// The interviewer announces the written coding questions with phrases like
// "hiring team" / "answer box" / "write your answer". Show the question panel
// only once the AI reaches that part of the interview.
function shouldStartTechQuestions(text) {
  return /hiring team|answer box|text box|type your answer|write your answer/i.test(text || "");
}

export function InterviewApp({ token, interviewType }) {
  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(null);
  const [result, setResult] = useState(null);
  const [customQuestions, setCustomQuestions] = useState([]);

  const [activeIndex, setActiveIndex] = useState(0);
  const [draft, setDraft] = useState("");
  const [showAllQuestions, setShowAllQuestions] = useState(false);
  const [techPhase, setTechPhase] = useState("hidden"); // "hidden" | "question" | "done"

  const [isAiThinking, setIsAiThinking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isMicActive, setIsMicActive] = useState(false);
  const [isAudioStreaming, setIsAudioStreaming] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);

  // Pre-flight device check (instruction page): grant camera+mic before the
  // interview starts so no permission prompt appears once fullscreen opens.
  const [deviceCheckStatus, setDeviceCheckStatus] = useState("idle"); // "idle" | "requesting" | "granted" | "denied"
  const [deviceCheckStream, setDeviceCheckStream] = useState(null);

  const liveRef = useRef(null);
  const videoRef = useRef(null);
  const transcriptRef = useRef([]);
  const streamingRef = useRef({ role: null, text: "" });
  const answeredRef = useRef(new Set());
  const skippedRef = useRef(new Set());
  const techPhaseRef = useRef("hidden");
  const activeIndexRef = useRef(0);
  const transcriptListRef = useRef(null);

  // ── Browser proctoring (tab switch / minimize / focus loss / fullscreen) ──
  // Strike 1 → warning modal; Strike 2 → auto-submit via endInterview().
  const proctoring = useProctoring({
    enabled: true,
    assessmentStarted: phase === "live",
    onAutoSubmit: () => {
      console.warn("[proctoring] Strike 2 — auto-submitting interview");
      endInterview();
    },
  });

  // Fetch session data
  useEffect(() => {
    fetch(`${API_BASE}/api/interview/session/${encodeURIComponent(token)}`)
      .then((response) => {
        if (!response.ok) throw new Error("Interview session not found");
        return response.json();
      })
      .then((data) => {
        setSession(data);
        setCustomQuestions(data.customQuestions || []);
        if (data.completed) {
          setPhase("done");
          setResult({ decision: data.decision, score: data.score });
        } else {
          setPhase("ready");
        }
      })
      .catch((err) => {
        setError(err.message);
        setPhase("error");
      });
  }, [token]);

  // Auto-scroll only the transcript panel (never the whole page) so the
  // question box appearing below does not cause the page to jump.
  useEffect(() => {
    const list = transcriptListRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [messages, streaming, isAiThinking]);

  function finalizeStreaming() {
    if (streamingRef.current.text.trim()) {
      const msg = {
        role: streamingRef.current.role,
        content: streamingRef.current.text.trim(),
      };
      setMessages((prev) => [...prev, msg]);
      transcriptRef.current = [...transcriptRef.current, msg];
    }
    streamingRef.current = { role: null, text: "" };
    setStreaming(null);
  }

  // Once the AI announces the written coding questions, reveal the panel and
  // show the first unanswered question.
  function checkTechTransition(text) {
    if (!isTechnical || !customQuestions.length || techPhaseRef.current !== "hidden") return;
    if (!shouldStartTechQuestions(text)) return;
    techPhaseRef.current = "question";
    activeIndexRef.current = 0;
    setTechPhase("question");
    setActiveIndex(0);
    setDraft("");
  }

  function nextUnansweredIndex(fromIndex) {
    for (let offset = 1; offset <= customQuestions.length; offset += 1) {
      const index = (fromIndex + offset) % customQuestions.length;
      const id = customQuestions[index].id;
      if (!answeredRef.current.has(id) && !skippedRef.current.has(id)) return index;
    }
    return -1;
  }

  function advanceToNextUnanswered() {
    const next = nextUnansweredIndex(activeIndexRef.current);
    if (next === -1) {
      techPhaseRef.current = "done";
      setTechPhase("done");
      return;
    }
    activeIndexRef.current = next;
    setActiveIndex(next);
    setDraft("");
  }

  // When the AI announces the next custom question ("...from the hiring team")
  // and the currently displayed question was already answered or skipped,
  // move the textbox on to the next unanswered question. This keeps the panel
  // in sync when the candidate skips a question via voice.
  function checkQuestionAnnouncement(text) {
    if (!isTechnical || !customQuestions.length || techPhaseRef.current === "hidden") return;
    if (!/hiring team/.test(text || "")) return;
    const current = customQuestions[activeIndexRef.current];
    const resolved =
      !current ||
      answeredRef.current.has(current.id) ||
      skippedRef.current.has(current.id);
    if (!resolved) return;
    advanceToNextUnanswered();
  }

  // ── Live voice interview (Gemini Live via backend relay) ─────────────────

  const uploadRecording = useCallback(async (interviewType) => {
    const client = liveRef.current;
    if (!client) return;
    try {
      const blob = await client.stopRecording();
      if (!blob || blob.size === 0) return;
      const formData = new FormData();
      formData.append("file", blob, "recording.webm");
      formData.append("token", token);
      formData.append("interview_type", interviewType);
      await fetch(`${API_BASE}/api/interview/recording/upload`, {
        method: "POST",
        body: formData,
      });
      console.log("[interview] recording uploaded", { size: blob.size });
    } catch (err) {
      console.error("[interview] recording upload failed:", err);
    }
  }, [token]);

  // ── Pre-flight device check (instruction page) ───────────────────────────

  async function requestDeviceAccess() {
    setDeviceCheckStatus("requesting");
    try {
      // Same constraints the live client uses during the interview.
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      setDeviceCheckStream(stream);
      setDeviceCheckStatus("granted");
    } catch (err) {
      // Camera missing/denied — fall back to mic-only so the candidate
      // without a camera is not dead-ended.
      console.warn("[device-check] camera+mic request failed:", err.message);
      try {
        const audioOnly = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        setDeviceCheckStream(audioOnly);
        setDeviceCheckStatus("granted");
      } catch (err2) {
        console.warn("[device-check] mic-only request failed:", err2.message);
        setDeviceCheckStatus("denied");
      }
    }
  }

  // Stop pre-check tracks if the candidate leaves before starting the
  // interview. Once handed to the live client, close() stops them anyway —
  // track.stop() is idempotent.
  useEffect(() => {
    return () => {
      setDeviceCheckStream((stream) => {
        if (stream) stream.getTracks().forEach((track) => track.stop());
        return null;
      });
    };
  }, []);

  async function startLive() {
    setIsAudioStreaming(false);
    const client = createLiveClient({
      token,
      initialStream: deviceCheckStream,
      onReady: () => {
        setIsMicActive(true);
        // Attach camera preview and start recording
        const camStream = client.getCameraStream();
        if (camStream) setCameraStream(camStream);
        client.startRecording();
        setIsRecording(true);
      },
      onAudioStreaming: () => setIsAudioStreaming(true),
      onTranscript: (role, text) => {
        if (!text) return;
        if (streamingRef.current.role !== role) {
          finalizeStreaming();
          streamingRef.current = { role, text };
        } else {
          streamingRef.current.text += ` ${text}`;
        }
        setStreaming({ role, text: streamingRef.current.text });
        if (role === "interviewer") {
          setIsAiSpeaking(true);
          checkTechTransition(streamingRef.current.text);
          checkQuestionAnnouncement(streamingRef.current.text);
        }
      },
      onTurnComplete: () => {
        setIsAiSpeaking(false);
        finalizeStreaming();
        const last = transcriptRef.current[transcriptRef.current.length - 1];
        if (last && last.role === "interviewer") {
          checkTechTransition(last.content);
          checkQuestionAnnouncement(last.content);
        }
      },
      onEvaluation: async (data) => {
        finalizeStreaming();
        // Stop recording and upload before showing results
        if (liveRef.current) {
          setIsRecording(false);
          await uploadRecording(interviewType);
        }
        setResult(data);
        setPhase("done");
        client.close();
      },
      onError: (message) => setError(message),
      onClosed: () => setIsMicActive(false),
    });
    liveRef.current = client;
    try {
      await client.connect();
    } catch (err) {
      setError("Live audio is unavailable on this device.");
    }
  }

  // ── Controls ─────────────────────────────────────────────────────────────

  function toggleMic() {
    const client = liveRef.current;
    if (!client) return;
    if (isMicActive) {
      client.pause();
      setIsMicActive(false);
    } else {
      client.resume();
      setIsMicActive(true);
    }
  }

  async function endInterview() {
    if (liveRef.current) {
      setIsRecording(false);
      await uploadRecording(interviewType);
      await liveRef.current.close();
    }
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setPhase("evaluating");

    try {
      const response = await fetch(`${API_BASE}/api/interview/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          transcript: transcriptRef.current,
          interview_type: interviewType,
        }),
      });
      if (!response.ok) {
        setError("Evaluation failed — try again");
        setPhase("done");
        return;
      }
      const data = await response.json();
      setResult(data);
      setPhase("done");
    } catch (err) {
      setError(err.message);
      setPhase("done");
    }
  }

  async function startInterview() {
    setPhase("live");
    setError("");
    setIsRecording(false);
    setCameraStream(null);
    answeredRef.current.clear();
    skippedRef.current.clear();
    techPhaseRef.current = "hidden";
    activeIndexRef.current = 0;
    setTechPhase("hidden");
    setActiveIndex(0);
    setDraft("");
    setShowAllQuestions(false);
    await startLive();
  }

  function submitAnswer(question, text) {
    const answer = (text || "").trim();
    if (!answer) {
      // Clicked submit without writing anything — tell the AI so it responds
      // honestly ("no written answer received") instead of claiming it saw one.
      skippedRef.current.add(question.id);
      if (liveRef.current) {
        liveRef.current.sendAnswer({ text: "", question: question.question });
      }
      return;
    }
    answeredRef.current.add(question.id);
    skippedRef.current.delete(question.id);
    const msg = {
      role: "candidate",
      content: answer,
      type: "written",
      question: question.question,
    };
    setMessages((prev) => [...prev, msg]);
    transcriptRef.current = [...transcriptRef.current, msg];
    if (liveRef.current) {
      liveRef.current.sendAnswer({ text: answer, question: question.question });
    }
    advanceToNextUnanswered();
  }

  const isTechnical = interviewType === "technical";
  const typeLabel = isTechnical ? "Technical" : "HR";
  const activeQuestion = customQuestions[activeIndex] || null;

  return (
    <div className="interview-app">
      <header className="interview-header">
        <div>
          <span className={`pill ${isTechnical ? "pill-tech" : "pill-hr"}`}>
            {typeLabel} AI Interview
          </span>
          <h1>{session?.candidateName || "Candidate"} · {session?.jobTitle || ""}</h1>
          <p>{session?.companyName} · {typeLabel} screening interview</p>
        </div>
        {phase === "live" || phase === "evaluating" ? (
          <button className="secondary-button danger" onClick={endInterview} disabled={phase === "evaluating"}>
            {phase === "evaluating" ? <Loader2 className="spin" size={17} /> : <PhoneOff size={17} />}
            End Interview
          </button>
        ) : null}
      </header>

      <div className="interview-body">
        {error ? <div className="notice error">{error}</div> : null}

        {phase === "loading" && (
          <div className="interview-stage">
            <Loader2 className="spin" size={26} />
            <strong>Loading interview session</strong>
          </div>
        )}

        {phase === "error" && (
          <div className="interview-stage">
            <XCircle size={26} />
            <strong>Session unavailable</strong>
            <span>{error}</span>
          </div>
        )}

        {/* ─── Instructions Page ─── */}
        {phase === "ready" && (
          <div className="interview-instructions">
            <div className="instructions-hero">
              <div className={`type-badge ${isTechnical ? "type-tech" : "type-hr"}`}>
                {isTechnical ? <Monitor size={22} /> : <UsersRound size={22} />}
                <span>{typeLabel} Interview</span>
              </div>
              <h2>Welcome, {session?.candidateName || "Candidate"}</h2>
              <p>You are about to begin your <strong>{typeLabel} AI Interview</strong> for the <strong>{session?.jobTitle}</strong> position at <strong>{session?.companyName}</strong>.</p>
            </div>

            <div className="instructions-grid">
              <div className="instruction-card">
                <div className="instruction-icon blue"><Clock size={20} /></div>
                <h4>Time Management</h4>
                <p>Take your time to think before answering. Quality matters more than speed.</p>
              </div>
              <div className="instruction-card">
                <div className="instruction-icon green"><Mic size={20} /></div>
                <h4>Clear Communication</h4>
                <p>Speak clearly and ensure your microphone is working properly before starting.</p>
              </div>
              <div className="instruction-card">
                <div className="instruction-icon purple"><Video size={20} /></div>
                <h4>Quiet Environment</h4>
                <p>Find a quiet space to minimize distractions during the interview.</p>
              </div>
              <div className="instruction-card">
                <div className="instruction-icon amber"><CheckCircle2 size={20} /></div>
                <h4>Be Yourself</h4>
                <p>Answer honestly and showcase your genuine skills and experiences.</p>
              </div>
            </div>

            {isTechnical ? (
              <div className="instructions-note">
                <Info size={18} />
                <p><strong>Technical Interview:</strong> You will be asked about your technical background, solve coding problems verbally, discuss system design, and answer questions about your projects. Think out loud and explain your reasoning.</p>
              </div>
            ) : (
              <div className="instructions-note">
                <Info size={18} />
                <p><strong>HR Interview:</strong> This interview covers your background, motivations, behavioral scenarios, cultural fit, and practical matters. Be prepared to share specific examples using the STAR method.</p>
              </div>
            )}

            {isTechnical && customQuestions.length > 0 ? (
              <div className="instructions-note">
                <Code2 size={18} />
                <p><strong>Coding Questions:</strong> The interviewer may also ask you coding questions from the company's question bank. When a coding question is asked, a <strong>textbox</strong> will appear below the conversation for you to type your answer.</p>
              </div>
            ) : null}

            <div className="instructions-note">
              <ShieldAlert size={18} />
              <p><strong>Proctoring Rules:</strong> This interview is proctored. It must be completed in <strong>fullscreen mode</strong>, and switching tabs, minimizing the window, or losing window focus is monitored. Your first violation triggers a warning; a second violation will automatically submit your interview.</p>
            </div>

            {/* ─── Pre-flight Device Check ─── */}
            <div className="device-check-card">
              <div className="device-check-header">
                <div className="instruction-icon blue"><Video size={20} /></div>
                <div>
                  <h4>Camera &amp; Microphone Check</h4>
                  <p>Allow access now so the interview can start instantly in fullscreen — no permission popups afterwards.</p>
                </div>
              </div>

              {deviceCheckStatus === "idle" && (
                <button type="button" className="primary-button device-check-btn" onClick={requestDeviceAccess}>
                  <Video size={18} />
                  Allow Camera &amp; Microphone
                </button>
              )}

              {deviceCheckStatus === "requesting" && (
                <div className="device-check-status">
                  <Loader2 className="spin" size={18} />
                  <span>Waiting for permission… please accept the browser prompt.</span>
                </div>
              )}

              {deviceCheckStatus === "granted" && (
                <div className="device-check-granted">
                  <div className="device-check-preview">
                    {deviceCheckStream && deviceCheckStream.getVideoTracks().length > 0 ? (
                      <video
                        ref={(el) => {
                          if (el && deviceCheckStream && el.srcObject !== deviceCheckStream) {
                            el.srcObject = deviceCheckStream;
                            el.play().catch(() => {});
                          }
                        }}
                        className="camera-preview"
                        autoPlay
                        muted
                        playsInline
                      />
                    ) : (
                      <div className="camera-preview camera-placeholder">
                        <Mic size={28} />
                      </div>
                    )}
                  </div>
                  <div className="device-check-status ok">
                    <CheckCircle2 size={18} />
                    <span>
                      {deviceCheckStream && deviceCheckStream.getVideoTracks().length > 0
                        ? "Camera & microphone ready."
                        : "Microphone ready (no camera detected)."}
                    </span>
                  </div>
                </div>
              )}

              {deviceCheckStatus === "denied" && (
                <div className="device-check-status error">
                  <XCircle size={18} />
                  <span>
                    Access was blocked. Enable camera &amp; microphone for this site in your browser settings, then try again.
                  </span>
                  <button type="button" className="secondary-button small" onClick={requestDeviceAccess}>
                    Try Again
                  </button>
                </div>
              )}
            </div>

            <div className="start-section">
              <h3>Ready to Begin?</h3>
              {deviceCheckStatus === "granted" ? (
                <p>You're all set. Clicking Start will enter fullscreen and begin the interview immediately.</p>
              ) : (
                <p>First allow your camera and microphone above. When you click Start Interview, fullscreen will open and the AI interviewer will begin the conversation.</p>
              )}
              <p className="recording-notice"><Video size={15} /> This interview will be recorded for quality and evaluation purposes.</p>
              <button
                className="primary-button start-btn"
                onClick={startInterview}
                disabled={deviceCheckStatus !== "granted"}
              >
                <Video size={19} />
                Start {typeLabel} Interview
              </button>
            </div>
          </div>
        )}

        {/* ─── Live Interview (browser audio ↔ Gemini Live relay) ─── */}
        {(phase === "live" || phase === "evaluating") && (
          <div className="interview-live-container">
            <div className="live-grid">
              {/* Left — AI avatar visual + camera preview */}
              <div className="ai-avatar-card">
                {/* Camera preview */}
                <div className="camera-preview-container">
                  {cameraStream ? (
                    <video
                      ref={(el) => {
                        if (el && cameraStream && el.srcObject !== cameraStream) {
                          el.srcObject = cameraStream;
                          el.play().catch(() => {});
                        }
                      }}
                      className="camera-preview"
                      autoPlay
                      muted
                      playsInline
                    />
                  ) : (
                    <div className="camera-preview camera-placeholder">
                      <VideoOff size={28} />
                    </div>
                  )}
                  {isRecording && (
                    <span className="recording-badge">
                      <span className="recording-dot" /> Recording
                    </span>
                  )}
                </div>

                <div
                  className={`ai-avatar ${
                    isAiSpeaking
                      ? "speaking"
                      : isAiThinking
                        ? "thinking"
                        : isMicActive
                          ? "listening"
                          : "idle"
                  }`}
                >
                  <span className="avatar-ring ring-1" />
                  <span className="avatar-ring ring-2" />
                  <span className="avatar-ring ring-3" />
                  <div className="avatar-core">
                    {isAiSpeaking ? (
                      <Volume2 size={46} />
                    ) : isAiThinking ? (
                      <Loader2 className="spin" size={46} />
                    ) : (
                      <Bot size={46} />
                    )}
                  </div>
                </div>

                <div className="ai-avatar-status">
                  <span
                    className={`status-dot ${
                      isAiSpeaking ? "speaking" : isAiThinking ? "thinking" : isMicActive ? "listening" : "idle"
                    }`}
                  />
                  <span>
                    {isAiSpeaking
                      ? "AI Interviewer is speaking…"
                      : isAiThinking
                        ? "AI Interviewer is thinking…"
                        : isMicActive
                          ? isAudioStreaming
                            ? "Listening — please speak now"
                            : "Checking microphone… speak to confirm"
                          : "Microphone paused"}
                  </span>
                </div>

                <div className="avatar-mic-row">
                  <button
                    type="button"
                    className={`mic-toggle-btn ${isMicActive ? "active" : ""}`}
                    onClick={toggleMic}
                    title={isMicActive ? "Pause Mic" : "Start Mic"}
                  >
                    {isMicActive ? <Mic size={22} /> : <MicOff size={22} />}
                  </button>
                  <span className="mic-toggle-hint">
                    {isMicActive ? "Tap to mute" : "Tap to unmute"}
                  </span>
                </div>
              </div>

              {/* Right — live transcript */}
              <div className="interview-transcript-panel">
                <div className="transcript-panel-header">
                  <h3>Live Transcript</h3>
                  <span className="transcript-count">{messages.length} turns</span>
                </div>
                <div className="transcript-list" ref={transcriptListRef}>
                  {messages.map((message, index) => (
                    <div key={index} className={`chat-bubble ${message.role}${message.type === "written" ? " written" : ""}`}>
                      <strong>
                        {message.type === "written"
                          ? "You (written answer)"
                          : message.role === "candidate"
                            ? "You"
                            : "AI Interviewer"}
                      </strong>
                      <p>{message.content}</p>
                    </div>
                  ))}
                  {streaming ? (
                    <div className={`chat-bubble ${streaming.role}`}>
                      <strong>{streaming.role === "candidate" ? "You" : "AI Interviewer"}</strong>
                      <p>{streaming.text}</p>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>

            {/* ─── Custom coding questions (written answer box) ─── */}
            {isTechnical && customQuestions.length > 0 && techPhase !== "hidden" && (
              <div className="question-bank">
                <div className="question-bank-header">
                  <div>
                    <h3><Code2 size={16} /> Coding Questions</h3>
                    <span className="question-bank-count">{answeredRef.current.size} of {customQuestions.length} answered</span>
                  </div>
                  <button type="button" className="secondary-button small" onClick={() => setShowAllQuestions((value) => !value)}>
                    {showAllQuestions ? "Hide list" : "Show all questions"}
                  </button>
                </div>

                {showAllQuestions ? (
                  <div className="question-all-list">
                    {customQuestions.map((question, index) => {
                      const isAnswered = answeredRef.current.has(question.id);
                      return (
                        <div key={question.id} className={`question-item ${isAnswered ? "answered" : ""}`}>
                          <div className="question-text">
                            <strong>{index + 1}. {question.question}</strong>
                            <span className="question-tags">{question.topic} · {question.difficulty}</span>
                          </div>
                          {isAnswered ? (
                            <div className="saved-answer">
                              <CheckCircle2 size={15} /> Answer submitted
                            </div>
                          ) : (
                            <AllQuestionForm question={question} onSubmit={submitAnswer} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : techPhase === "done" ? (
                  <div className="active-question done">
                    <CheckCircle2 size={18} />
                    All coding questions answered — great work!
                  </div>
                ) : activeQuestion ? (
                  <div className="active-question">
                    <div className="question-text">
                      <strong>Question {activeIndex + 1} of {customQuestions.length}: {activeQuestion.question}</strong>
                      <span className="question-tags">{activeQuestion.topic} · {activeQuestion.difficulty}</span>
                    </div>
                    <textarea
                      rows={5}
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder="Type your code / technical answer here…"
                    />
                    <button type="button" className="primary-button submit-answer" onClick={() => submitAnswer(activeQuestion, draft)}>
                      Submit Answer
                    </button>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}

        {/* ─── Candidate Completion Confirmation (No Score/Feedback Shown) ─── */}
        {phase === "done" && (
          <div className="interview-results">
            <div className="result-hero">
              <div className="result-icon pass"><CheckCircle2 size={42} /></div>
              <h2>Interview Submitted Successfully</h2>
              <p className="completion-message">
                Thank you for your time, <strong>{session?.candidateName || "Candidate"}</strong>! Your <strong>{typeLabel} AI Interview</strong> responses have been recorded and submitted.
              </p>
              <div className="instructions-note">
                <Info size={20} />
                <p>Our recruitment team will review your interview session. You will be contacted soon regarding the next steps in the hiring process.</p>
              </div>
              <p className="result-thanks">You may safely close this browser window now.</p>
            </div>
          </div>
        )}
        {/* ─── Proctoring warning modal (Strike 1) ─── */}
        <ProctoringWarningModal activeWarning={proctoring.activeWarning} onResume={proctoring.dismissWarning} />
      </div>
    </div>
  );
}

function AllQuestionForm({ question, onSubmit }) {
  const [text, setText] = useState("");
  return (
    <div className="all-question-form">
      <textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} placeholder="Type your answer…" />
      <button
        type="button"
        className="primary-button submit-answer"
        onClick={() => {
          onSubmit(question, text);
          setText("");
        }}
      >
        Submit
      </button>
    </div>
  );
}
