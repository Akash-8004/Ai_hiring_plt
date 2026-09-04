/* Client for the Gemini Live voice interview with video recording.

   Captures mic + camera, streams mic PCM (16kHz) to the FastAPI WebSocket
   relay, and plays back Gemini's 24kHz PCM audio.

   A MediaRecorder records the candidate's camera video mixed with both mic
   audio and the AI interviewer's voice.  The recording is assembled into a
   single WebM Blob when stopRecording() is called.

   Capture uses ScriptProcessorNode for broad browser compatibility. */

const API_BASE = import.meta.env.VITE_API_BASE || "";
const OUTPUT_SAMPLE_RATE = 24000;

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function wsUrl(token) {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/interview/${encodeURIComponent(token)}`;
}

function decodePcm(b64) {
  const raw = atob(b64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const samples = new Float32Array(bytes.length / 2);
  for (let i = 0, j = 0; i + 1 < bytes.length; i += 2, j++) {
    const value = bytes[i] | (bytes[i + 1] << 8);
    samples[j] = (value > 32767 ? value - 65536 : value) / 32768;
  }
  return samples;
}

export function createLiveClient({ token, initialStream = null, onReady, onTranscript, onTurnComplete, onEvaluation, onError, onClosed, onAudioStreaming }) {
  let ws = null;
  let audioContext = null;
  let micStream = null;
  let cameraStream = null;
  let sourceNode = null;
  let captureNode = null;
  let closed = false;

  // ── Speaker playback queue (unchanged) ──
  let playbackSources = [];
  let pendingChunks = [];
  let playing = false;

  let framesSent = 0;

  // ── Recording state ──
  let recorder = null;
  let recordingChunks = [];
  let recordingResolve = null;
  let micForRecording = null;

  // ── AI audio → recording graph ──
  let aiAudioDestination = null;
  let aiCircularBuffer = new Float32Array(OUTPUT_SAMPLE_RATE * 10); // 10s ring buffer
  let aiBufferWritePos = 0;
  let aiBufferReadPos = 0;
  let aiProcessor = null;
  let aiSilentGain = null;

  // ── Playback (speaker) ──────────────────────────────────────────────

  function stopPlayback() {
    playbackSources.forEach((source) => {
      try {
        source.onended = null;
        source.stop();
      } catch (e) { /* already stopped */ }
    });
    playbackSources = [];
    playing = false;
  }

  function playNext() {
    if (playing || !audioContext || closed) return;
    const samples = pendingChunks.shift();
    if (!samples || samples.length === 0) return;

    const buffer = audioContext.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = () => {
      playing = false;
      playNext();
    };
    playbackSources = [source];
    playing = true;
    source.start();
  }

  function enqueuePcm(b64) {
    if (!audioContext || closed) return;
    const samples = decodePcm(b64);
    pendingChunks.push(samples);
    playNext();

    // Also feed into the AI audio recording graph
    feedAiAudioToRecorder(samples);
  }

  function clearPlayback() {
    pendingChunks = [];
    stopPlayback();
    // Clear the AI circular buffer on interrupt
    aiBufferWritePos = 0;
    aiBufferReadPos = 0;
  }

  // ── AI audio → MediaStreamDestination for recording ─────────────────

  function feedAiAudioToRecorder(samples) {
    if (!aiCircularBuffer || !audioContext) return;
    const buf = aiCircularBuffer;
    const srcRate = OUTPUT_SAMPLE_RATE; // 24 000 Hz from Gemini
    const dstRate = audioContext.sampleRate; // 44 100 / 48 000 Hz

    if (srcRate === dstRate) {
      for (let i = 0; i < samples.length; i++) {
        buf[aiBufferWritePos % buf.length] = samples[i];
        aiBufferWritePos++;
      }
      return;
    }

    // Linear-interpolation resample from srcRate → dstRate
    const numOut = Math.ceil(samples.length * dstRate / srcRate);
    for (let o = 0; o < numOut; o++) {
      const srcPos = o * srcRate / dstRate;
      const idx = Math.floor(srcPos);
      const frac = srcPos - idx;
      const s0 = idx < samples.length ? samples[idx] : 0;
      const s1 = idx + 1 < samples.length ? samples[idx + 1] : 0;
      buf[aiBufferWritePos % buf.length] = s0 + frac * (s1 - s0);
      aiBufferWritePos++;
    }
  }

  function startAiAudioGraph() {
    if (!audioContext) return;

    aiCircularBuffer = new Float32Array(Math.ceil(audioContext.sampleRate * 10));
    aiBufferWritePos = 0;
    aiBufferReadPos = 0;

    aiAudioDestination = audioContext.createMediaStreamDestination();

    // ScriptProcessor reads from circular buffer → feeds destination
    const bufferSize = 4096;
    aiProcessor = audioContext.createScriptProcessor(bufferSize, 0, 1);
    aiProcessor.onaudioprocess = (event) => {
      const output = event.outputBuffer.getChannelData(0);
      const buf = aiCircularBuffer;
      const available = aiBufferWritePos - aiBufferReadPos;
      const toRead = Math.min(output.length, available, buf.length);

      for (let i = 0; i < output.length; i++) {
        if (i < toRead) {
          output[i] = buf[aiBufferReadPos % buf.length];
          aiBufferReadPos++;
        } else {
          output[i] = 0;
        }
      }
    };

    // Silent gain keeps the processor alive in the render graph
    aiSilentGain = audioContext.createGain();
    aiSilentGain.gain.value = 0;

    aiProcessor.connect(aiSilentGain);
    aiSilentGain.connect(audioContext.destination);
    aiProcessor.connect(aiAudioDestination);
  }

  // ── Capture (mic + camera) ──────────────────────────────────────────

  async function startCapture() {
    if (initialStream) {
      // Stream was already granted during the pre-flight device check on the
      // instruction page — reuse it so no permission prompt appears now.
      cameraStream = initialStream;
      micStream = new MediaStream(cameraStream.getAudioTracks());
      console.log("[live] reusing pre-granted media stream", {
        camera: cameraStream.getVideoTracks().length > 0,
        mic: micStream.getAudioTracks().length > 0,
      });
    } else {
      // Request both camera and microphone
      try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        micStream = new MediaStream(cameraStream.getAudioTracks());
      } catch (e) {
        // Camera denied — fall back to audio-only
        console.warn("[live] camera access denied, proceeding audio-only:", e.message);
        cameraStream = null;
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      }
    }

    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === "suspended") await audioContext.resume();

    const TARGET_RATE = 16000;
    const ratio = audioContext.sampleRate / TARGET_RATE;
    const bufferSize = audioContext.sampleRate > 44100 ? 4096 : 2048;

    sourceNode = audioContext.createMediaStreamSource(micStream);
    captureNode = audioContext.createScriptProcessor(bufferSize, 1, 1);
    sourceNode.connect(captureNode);
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    captureNode.connect(silentGain);
    silentGain.connect(audioContext.destination);

    const outChunk = new Int16Array(TARGET_RATE / 10);
    let outPos = 0;
    let acc = [];

    captureNode.onaudioprocess = (event) => {
      const channel = event.inputBuffer.getChannelData(0);
      for (let i = 0; i < channel.length; i++) {
        acc.push(channel[i]);
        if (acc.length >= ratio) {
          let sum = 0;
          for (let j = 0; j < acc.length; j++) sum += acc[j];
          const sample = Math.max(-32767, Math.min(32767, Math.round((sum / acc.length) * 32767)));
          outChunk[outPos++] = sample;
          acc.length = 0;
        }
        if (outPos === outChunk.length) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            if (framesSent === 0) {
              console.log("[live] mic audio streaming to server");
              onAudioStreaming && onAudioStreaming();
            }
            framesSent += 1;
            ws.send(JSON.stringify({ type: "audio", data: toBase64(outChunk.buffer) }));
          }
          outPos = 0;
        }
      }
    };

    // Start the AI audio → recording graph
    startAiAudioGraph();

    // Set up mic track for recording (original sample rate, full quality)
    const micTracks = micStream.getAudioTracks();
    if (micTracks.length > 0) {
      micForRecording = micTracks[0];
    }

    console.log("[live] capture active", {
      sampleRate: audioContext.sampleRate,
      ratio,
      camera: !!cameraStream,
    });
  }

  // ── MediaRecorder ───────────────────────────────────────────────────

  function startRecording() {
    if (!audioContext || !aiAudioDestination) return;

    const streams = [];

    // Camera video track
    if (cameraStream) {
      const videoTracks = cameraStream.getVideoTracks();
      if (videoTracks.length > 0) streams.push(videoTracks[0]);
    }

    // Mixed audio: mic + AI interviewer voice
    if (micForRecording && aiAudioDestination) {
      const micStreamForRec = new MediaStream([micForRecording]);
      const micSourceNode = audioContext.createMediaStreamSource(micStreamForRec);
      const micDestination = audioContext.createMediaStreamDestination();
      micSourceNode.connect(micDestination);

      // Merge mic + AI audio into one stream
      const mergedDestination = audioContext.createMediaStreamDestination();
      const micMergeSource = audioContext.createMediaStreamSource(micDestination.stream);
      const aiMergeSource = audioContext.createMediaStreamSource(aiAudioDestination.stream);
      micMergeSource.connect(mergedDestination);
      aiMergeSource.connect(mergedDestination);

      streams.push(...mergedDestination.stream.getAudioTracks());
    }

    if (streams.length === 0) {
      console.warn("[live] no tracks available for recording");
      return;
    }

    const compositeStream = new MediaStream(streams);

    // Prefer webm with vp8+opus; fall back to whatever is available
    const mimeType =
      MediaRecorder.isTypeSupported("video/webm;codecs=vp8,opus")
        ? "video/webm;codecs=vp8,opus"
        : MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
          ? "video/webm;codecs=vp9,opus"
          : "video/webm";

    recorder = new MediaRecorder(compositeStream, {
      mimeType,
      videoBitsPerSecond: 250000,
      audioBitsPerSecond: 128000,
    });

    recordingChunks = [];

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordingChunks.push(event.data);
      }
    };

    recorder.onerror = (event) => {
      console.error("[live] MediaRecorder error:", event.error);
    };

    recorder.start(5000); // collect in 5-second chunks
    console.log("[live] recording started", { mimeType });
  }

  function stopRecording() {
    return new Promise((resolve) => {
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      recordingResolve = resolve;
      recorder.onstop = () => {
        const blob = new Blob(recordingChunks, { type: recorder.mimeType });
        console.log("[live] recording stopped", { size: blob.size });
        recordingChunks = [];
        recorder = null;
        recordingResolve && recordingResolve(blob);
        recordingResolve = null;
      };
      recorder.stop();
    });
  }

  // ── WebSocket ───────────────────────────────────────────────────────

  async function openSocket() {
    await new Promise((resolve, reject) => {
      ws = new WebSocket(wsUrl(token));
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("Could not connect to the live interview."));
    });
    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      switch (msg.type) {
        case "ready":
          onReady && onReady();
          break;
        case "audio":
          enqueuePcm(msg.data);
          break;
        case "interrupt":
          clearPlayback();
          break;
        case "transcript":
          onTranscript && onTranscript(msg.role, msg.text);
          break;
        case "turn_complete":
          onTurnComplete && onTurnComplete();
          break;
        case "evaluation":
          onEvaluation && onEvaluation(msg.result);
          break;
        case "error":
          onError && onError(msg.message);
          break;
        case "closed":
          onClosed && onClosed();
          break;
        default:
          break;
      }
    };
    ws.onclose = () => {
      onClosed && onClosed();
    };
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    async connect() {
      await startCapture();
      await openSocket();
    },
    getCameraStream() {
      return cameraStream;
    },
    pause() {
      if (sourceNode && captureNode) {
        try {
          sourceNode.disconnect(captureNode);
        } catch (e) { /* not connected */ }
      }
    },
    resume() {
      if (sourceNode && captureNode) {
        try {
          sourceNode.connect(captureNode);
        } catch (e) { /* already connected */ }
      }
    },
    sendAnswer({ text, question }) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: "answer", text, question }));
    },
    startRecording,
    stopRecording,
    async close() {
      closed = true;
      clearPlayback();
      if (recorder && recorder.state !== "inactive") {
        try { recorder.stop(); } catch (e) { /* ignore */ }
      }
      if (captureNode) captureNode.disconnect();
      if (sourceNode) sourceNode.disconnect();
      if (aiProcessor) { try { aiProcessor.disconnect(); } catch (e) {} }
      if (aiSilentGain) { try { aiSilentGain.disconnect(); } catch (e) {} }
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
      if (audioContext) {
        try {
          await audioContext.close();
        } catch (e) { /* already closed */ }
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "end" }));
        ws.close();
      }
    },
  };
}
