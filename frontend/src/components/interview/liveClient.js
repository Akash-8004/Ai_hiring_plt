/* Minimal client for the Gemini Live voice interview.
   Captures mic audio (16kHz PCM) and streams it to the FastAPI WebSocket relay.
   The relay decides what Gemini hears (energy-based voice-activity windowing) and
   streams synthesized audio + transcriptions back through a gap-free playback
   queue.

   Capture uses a ScriptProcessorNode (not an AudioWorklet): it is guaranteed to
   run in every browser once the AudioContext is running and the mic source is
   connected, and it removes the worklet module-caching/graph-pull failure modes.

   Gemini outputs audio at 24kHz, so playback buffers are created at that
   rate; the microphone input is downsampled to 16kHz before upload. */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
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

export function createLiveClient({ token, onReady, onTranscript, onTurnComplete, onEvaluation, onError, onClosed, onAudioStreaming }) {
  let ws = null;
  let audioContext = null;
  let micStream = null;
  let sourceNode = null;
  let captureNode = null;
  let closed = false;

  let playbackSources = [];
  let pendingChunks = [];
  let playing = false;

  let framesSent = 0;

  function stopPlayback() {
    playbackSources.forEach((source) => {
      try {
        source.onended = null;
        source.stop();
      } catch (e) {
        /* already stopped */
      }
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
    pendingChunks.push(decodePcm(b64));
    playNext();
  }

  function clearPlayback() {
    pendingChunks = [];
    stopPlayback();
  }

  async function startCapture() {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === "suspended") await audioContext.resume();

    const TARGET_RATE = 16000;
    const ratio = audioContext.sampleRate / TARGET_RATE;
    const bufferSize = audioContext.sampleRate > 44100 ? 4096 : 2048;

    sourceNode = audioContext.createMediaStreamSource(micStream);
    captureNode = audioContext.createScriptProcessor(bufferSize, 1, 1);
    sourceNode.connect(captureNode);
    // Guarantee the processor is pulled by the render graph. The node outputs
    // silence (we never write its output), so a gain of 0 keeps it inaudible
    // while ensuring onaudioprocess fires on every render quantum.
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    captureNode.connect(silentGain);
    silentGain.connect(audioContext.destination);

    const outChunk = new Int16Array(TARGET_RATE / 10); // 100ms of 16kHz PCM
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

    console.log("[live] microphone capture active", { sampleRate: audioContext.sampleRate, ratio });
  }

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

  return {
    async connect() {
      await startCapture();
      await openSocket();
    },
    pause() {
      if (sourceNode && captureNode) {
        try {
          sourceNode.disconnect(captureNode);
        } catch (e) {
          /* not connected */
        }
      }
    },
    resume() {
      if (sourceNode && captureNode) {
        try {
          sourceNode.connect(captureNode);
        } catch (e) {
          /* already connected */
        }
      }
    },
    sendAnswer({ text, question }) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: "answer", text, question }));
    },
    async close() {
      closed = true;
      clearPlayback();
      if (captureNode) captureNode.disconnect();
      if (sourceNode) sourceNode.disconnect();
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      if (audioContext) {
        try {
          await audioContext.close();
        } catch (e) {
          /* already closed */
        }
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "end" }));
        ws.close();
      }
    },
  };
}
