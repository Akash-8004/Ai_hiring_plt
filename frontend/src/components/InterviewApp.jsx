import React, { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Clock,
  Info,
  Loader2,
  Mic,
  MicOff,
  Monitor,
  PhoneOff,
  Send,
  UsersRound,
  Video,
  XCircle,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function InterviewApp({ token, interviewType }) {
  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [messages, setMessages] = useState([]);
  const [result, setResult] = useState(null);

  const [inputText, setInputText] = useState("");
  const [isAiThinking, setIsAiThinking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isMicActive, setIsMicActive] = useState(false);

  const recognitionRef = useRef(null);
  const transcriptRef = useRef([]);
  const messagesEndRef = useRef(null);

  // Initialize SpeechRecognition (STT)
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = "en-US";

      rec.onresult = (event) => {
        let text = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          text += event.results[i][0].transcript;
        }
        if (text.trim()) {
          setInputText(text);
        }
      };

      rec.onerror = (err) => {
        console.warn("SpeechRecognition notice:", err.error);
      };

      rec.onend = () => {
        setIsMicActive(false);
      };

      recognitionRef.current = rec;
    }
  }, []);

  function startMic() {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
        setIsMicActive(true);
      } catch (e) {
        /* already active or permission error */
      }
    }
  }

  function stopMic() {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
        setIsMicActive(false);
      } catch (e) {
        /* ignore */
      }
    }
  }

  function toggleMic() {
    if (isMicActive) {
      stopMic();
    } else {
      startMic();
    }
  }

  // Text-To-Speech (TTS)
  function speakAIResponse(text, onComplete) {
    if (!("speechSynthesis" in window)) {
      if (onComplete) onComplete();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(
      (v) =>
        v.lang.startsWith("en") &&
        (v.name.includes("Google") ||
          v.name.includes("Natural") ||
          v.name.includes("Samantha") ||
          v.name.includes("David"))
    );
    if (naturalVoice) utterance.voice = naturalVoice;

    setIsAiSpeaking(true);

    utterance.onend = () => {
      setIsAiSpeaking(false);
      if (onComplete) onComplete();
    };
    utterance.onerror = () => {
      setIsAiSpeaking(false);
      if (onComplete) onComplete();
    };

    window.speechSynthesis.speak(utterance);
  }

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
  }, [messages, isAiThinking]);

  // Start Interview Action
  async function startInterview() {
    setPhase("live");
    setError("");
    setIsAiThinking(true);

    try {
      // Request mic permission
      try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        console.warn("Microphone access prompt:", e);
      }

      // Call Backend LLM for Initial AI Greeting
      const res = await fetch(`${API_BASE}/api/interview/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          interview_type: interviewType,
          transcript: [],
          user_message: "",
        }),
      });

      if (!res.ok) throw new Error("Could not connect to AI interviewer");

      const data = await res.json();
      const initialMsg = { role: "interviewer", content: data.content };
      transcriptRef.current = [initialMsg];
      setMessages([initialMsg]);
      setIsAiThinking(false);

      // Speak opening greeting out loud, then activate mic for candidate response!
      speakAIResponse(data.content, () => {
        startMic();
      });
    } catch (err) {
      setError(err.message);
      setIsAiThinking(false);
    }
  }

  // Send candidate turn
  async function sendCandidateTurn(textToSend) {
    const text = (textToSend || inputText).trim();
    if (!text || isAiThinking) return;

    stopMic();
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    const candidateMsg = { role: "candidate", content: text };
    const updatedTranscript = [...transcriptRef.current, candidateMsg];
    transcriptRef.current = updatedTranscript;
    setMessages(updatedTranscript);
    setInputText("");
    setIsAiThinking(true);

    try {
      const res = await fetch(`${API_BASE}/api/interview/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          interview_type: interviewType,
          transcript: updatedTranscript,
          user_message: text,
        }),
      });

      if (!res.ok) throw new Error("Failed to get response from AI interviewer");

      const data = await res.json();
      const aiMsg = { role: "interviewer", content: data.content };
      const finalTranscript = [...updatedTranscript, aiMsg];
      transcriptRef.current = finalTranscript;
      setMessages(finalTranscript);
      setIsAiThinking(false);

      // Speak AI response, then restart mic for candidate's next turn
      speakAIResponse(data.content, () => {
        startMic();
      });
    } catch (err) {
      setError(err.message);
      setIsAiThinking(false);
    }
  }

  async function endInterview() {
    stopMic();
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

        {/* ─── Live Interview (STT -> LLM -> TTS) ─── */}
        {(phase === "live" || phase === "evaluating") && (
          <div className="interview-live-container">
            <div className="status-banner">
              {isAiThinking ? (
                <div className="banner-badge thinking">
                  <Loader2 className="spin" size={16} />
                  <span>AI Interviewer is thinking…</span>
                </div>
              ) : isAiSpeaking ? (
                <div className="banner-badge speaking">
                  <Mic size={16} />
                  <span>AI Interviewer is speaking…</span>
                </div>
              ) : isMicActive ? (
                <div className="banner-badge listening">
                  <Mic size={16} />
                  <span>Listening to your voice… (Speak now)</span>
                </div>
              ) : (
                <div className="banner-badge ready">
                  <MicOff size={16} />
                  <span>Mic paused — click Mic icon or type to answer</span>
                </div>
              )}
            </div>

            <div className="interview-chat-messages">
              {messages.map((message, index) => (
                <div key={index} className={`chat-bubble ${message.role}`}>
                  <strong>{message.role === "candidate" ? "You" : "AI Interviewer"}</strong>
                  <p>{message.content}</p>
                </div>
              ))}
              {isAiThinking && (
                <div className="chat-bubble interviewer thinking-bubble">
                  <strong>AI Interviewer</strong>
                  <p><Loader2 className="spin" size={16} /> Generating response…</p>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {phase === "live" && (
              <form
                className="chat-input-bar"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendCandidateTurn();
                }}
              >
                <button
                  type="button"
                  className={`mic-toggle-btn ${isMicActive ? "active" : ""}`}
                  onClick={toggleMic}
                  title={isMicActive ? "Pause Mic" : "Start Mic Recording"}
                >
                  {isMicActive ? <Mic size={20} /> : <MicOff size={20} />}
                </button>
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder={
                    isMicActive
                      ? "Listening to your voice… (or type here)"
                      : "Type your answer or click mic to speak…"
                  }
                  disabled={isAiThinking}
                />
                <button
                  type="submit"
                  className="primary-button send-btn"
                  disabled={!inputText.trim() || isAiThinking}
                >
                  <Send size={18} />
                  <span>Send</span>
                </button>
              </form>
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
      </div>
    </div>
  );
}
