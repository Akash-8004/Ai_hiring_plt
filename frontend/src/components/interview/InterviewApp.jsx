import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Clock,
  Info,
  Loader2,
  Mic,
  MicOff,
  Monitor,
  PhoneOff,
  UsersRound,
  Video,
  Volume2,
  XCircle,
} from "lucide-react";
import { createLiveClient } from "./liveClient";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function InterviewApp({ token, interviewType }) {
  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(null);
  const [result, setResult] = useState(null);

  const [isAiThinking, setIsAiThinking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isMicActive, setIsMicActive] = useState(false);
  const [isAudioStreaming, setIsAudioStreaming] = useState(false);

  const liveRef = useRef(null);
  const transcriptRef = useRef([]);
  const streamingRef = useRef({ role: null, text: "" });
  const messagesEndRef = useRef(null);

  // Fetch session data
  useEffect(() => {
    fetch(`${API_BASE}/api/interview/session/${encodeURIComponent(token)}`)
      .then((response) => {
        if (!response.ok) throw new Error("Interview session not found");
        return response.json();
      })
      .then((data) => {
        setSession(data);
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

  // Auto scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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

  // ── Live voice interview (Gemini Live via backend relay) ─────────────────

  async function startLive() {
    setIsAudioStreaming(false);
    const client = createLiveClient({
      token,
      onReady: () => setIsMicActive(true),
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
        if (role === "interviewer") setIsAiSpeaking(true);
      },
      onTurnComplete: () => {
        setIsAiSpeaking(false);
        finalizeStreaming();
      },
      onEvaluation: (data) => {
        finalizeStreaming();
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
    await startLive();
  }

  const isTechnical = interviewType === "technical";
  const typeLabel = isTechnical ? "Technical" : "HR";

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

            <div className="start-section">
              <h3>Ready to Begin?</h3>
              <p>When you click Start Interview, your microphone will be activated and the AI interviewer will begin the conversation.</p>
              <button className="primary-button start-btn" onClick={startInterview}>
                <Mic size={19} />
                Start {typeLabel} Interview
              </button>
            </div>
          </div>
        )}

        {/* ─── Live Interview (browser audio ↔ Gemini Live relay) ─── */}
        {(phase === "live" || phase === "evaluating") && (
          <div className="interview-live-container">
            <div className="live-grid">
              {/* Left — AI avatar visual */}
              <div className="ai-avatar-card">
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
                <div className="transcript-list">
                  {messages.map((message, index) => (
                    <div key={index} className={`chat-bubble ${message.role}`}>
                      <strong>{message.role === "candidate" ? "You" : "AI Interviewer"}</strong>
                      <p>{message.content}</p>
                    </div>
                  ))}
                  {streaming ? (
                    <div className={`chat-bubble ${streaming.role}`}>
                      <strong>{streaming.role === "candidate" ? "You" : "AI Interviewer"}</strong>
                      <p>{streaming.text}</p>
                    </div>
                  ) : null}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </div>
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
      </div>
    </div>
  );
}
