// Configuration (mocked OpenAI-compatible pipeline by default)
const USE_MOCK_API = false;
const USE_WS_ANALYSIS = true; // Stream mic audio to backend WS
const OPENAI_COMPAT_API_BASE = 'http://localhost:8000';
const JOKE_API_BASE = 'http://localhost:8001';

// State
let autoScrollEnabled = true;
let sessionRunning = false;
let audioCtx = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let analysisTimer = null;
let analysisCanvas = null;
let analysisCtx2d = null;
let lastAudioRms = 0;

// WebSocket analysis state
let wsAnalyze = null;
let resampleState = { tail: new Float32Array(0), t: 0 };
const TARGET_SR = 24000;
let lastJokeTs = 0;
let jokeInFlight = false;
let fallbackJokeTimer = null;
const JOKE_COOLDOWN_MS = 1200; // minimum gap between generations
const JOKE_FALLBACK_MS = 3000; // auto-joke if no reaction within this window
let audioPlaying = false;
let visualTimer = null;
let timelineEvents = [];
let lastJokeText = '';
let lastJokeAt = 0;
let lastJokeEndAt = 0;
let jokeSeq = 0;
let activeJokeId = null;
let fallbackTimeout = null;
let latestAudioAnalysis = null;
let latestVisualAnalysis = null;
const DEBUG_CONTEXT = true;
const POST_TTS_DELAY_MS = 450;
const MIN_MESSAGE_GAP_MS = 900;
let speechQueue = [];
let drainingSpeechQueue = false;
let lastSpokenAt = 0;
let currentAudioEl = null;
// Reaction plot state
let reactionSeries = [];
let reactionCanvas = null;
let reactionCtx = null;
const REACTION_WINDOW_MS = 30000; // last 30s
let reactionAnimationHandle = null;

// Elements
const logsContainer = document.getElementById('logs-container');
const startBtn = document.getElementById('start-session');
const sessionStatus = document.getElementById('session-status');
const cameraPreview = document.getElementById('camera-preview');
const micStatus = document.getElementById('mic-status');
const micDot = document.getElementById('mic-dot');
const statusText = document.getElementById('status-text');

// Modal
const modal = document.getElementById('response-modal');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const modalClose = document.querySelector('.modal-close');
const modalCopy = document.getElementById('modal-copy');

function showModal(title, content) {
    if (!modal) return;
    modalTitle.textContent = title;
    modalBody.textContent = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
    modal.classList.add('show');
}

function hideModal() {
    if (!modal) return;
    modal.classList.remove('show');
}

if (modalClose) modalClose.onclick = hideModal;
window.onclick = (e) => { if (e.target === modal) hideModal(); };
if (modalCopy) {
    modalCopy.onclick = () => {
        navigator.clipboard.writeText(modalBody.textContent);
        modalCopy.textContent = 'Copied!';
        setTimeout(() => { modalCopy.textContent = 'Copy to Clipboard'; }, 2000);
    };
}

// Stream backend logs via Server-Sent Events
function connectServiceLogs(serviceName, url) {
    try {
        const es = new EventSource(url);
        es.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                addLog(data.service || serviceName, data.message || '', data.level || 'info');
            } catch (_) {
                addLog(serviceName, evt.data, 'info');
            }
        };
        es.onerror = () => {
            addLog(serviceName, 'Log stream disconnected; retrying...', 'warning');
            es.close();
            setTimeout(() => connectServiceLogs(serviceName, url), 3000);
        };
        addLog('system', `Connected to ${serviceName} logs`, 'success');
    } catch (e) {
        addLog('system', `Failed to connect ${serviceName} logs: ${e.message}`, 'error');
    }
}

window.addEventListener('load', () => {
    connectServiceLogs('audience', `${OPENAI_COMPAT_API_BASE}/stream/logs`);
    connectServiceLogs('joke', `${JOKE_API_BASE}/stream/logs`);
    initReactionPlot();
});

// Logging
function addLog(service, message, level = 'info') {
    if (!logsContainer) return;
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    const timestamp = new Date().toLocaleTimeString();
    entry.innerHTML = `
        <div>
            <span class="timestamp">${timestamp}</span>
            <span class="service">${service}</span>
        </div>
        <div class="message">${escapeHtml(String(message))}</div>
    `;
    logsContainer.appendChild(entry);
    if (autoScrollEnabled) entry.scrollIntoView({ behavior: 'smooth' });
    while (logsContainer.children.length > 200) logsContainer.removeChild(logsContainer.firstChild);
}

const clearLogsBtn = document.getElementById('clear-logs');
if (clearLogsBtn) clearLogsBtn.onclick = () => { logsContainer.innerHTML = ''; addLog('system', 'Logs cleared', 'info'); };
const toggleAutoScrollBtn = document.getElementById('toggle-autoscroll');
if (toggleAutoScrollBtn) toggleAutoScrollBtn.onclick = (e) => { autoScrollEnabled = !autoScrollEnabled; e.target.textContent = `Auto-scroll: ${autoScrollEnabled ? 'ON' : 'OFF'}`; };

// Audio visualization
function updateMicLevel(level) {
    const lvl = Math.max(0, Math.min(1, level));
    const pct = Math.round(lvl * 100);
    const bar = document.getElementById('mic-level');
    if (bar) {
        bar.style.width = pct + '%';
        if (lvl > 0.25) bar.classList.add('hot'); else bar.classList.remove('hot');
    }
}

// Session control
async function startSession() {
    if (sessionRunning) return;
    try {
        // Reset context/session state for a fresh run
        try {
            jokeSeq = 0;
            activeJokeId = null;
            lastJokeText = '';
            lastJokeAt = 0;
            lastJokeTs = 0;
            jokeInFlight = false;
            audioPlaying = false;
            timelineEvents = [];
            if (fallbackTimeout) { clearTimeout(fallbackTimeout); fallbackTimeout = null; }
            // Reset server-side comedian session
            fetch(`${JOKE_API_BASE}/reset`, { method: 'POST' }).catch(() => {});
        } catch (_) {}

        statusText && (statusText.textContent = 'Requesting permissions...');
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
            video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'environment' }
        });

        mediaStream = stream;
        if (cameraPreview) {
            cameraPreview.srcObject = stream;
            const playPromise = cameraPreview.play();
            if (playPromise && typeof playPromise.then === 'function') {
                playPromise.catch(() => {});
            }
        }

        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        sourceNode = audioCtx.createMediaStreamSource(stream);
        processorNode = audioCtx.createScriptProcessor(4096, 1, 1);
        sourceNode.connect(processorNode);
        processorNode.connect(audioCtx.destination);
        processorNode.onaudioprocess = (e) => {
            const input = e.inputBuffer.getChannelData(0);
            let sum = 0;
            for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
            const rms = Math.sqrt(sum / input.length) || 0;
            lastAudioRms = (lastAudioRms * 0.8) + (rms * 0.2);
            updateMicLevel(lastAudioRms);

            if (USE_WS_ANALYSIS) {
                try {
                    const { out, state } = resampleTo16kPCM16(input, audioCtx.sampleRate, resampleState);
                    resampleState = state;
                    if (wsAnalyze && wsAnalyze.readyState === WebSocket.OPEN && out.length > 0) {
                        const b64 = u8ToBase64(new Uint8Array(out.buffer));
                        wsAnalyze.send(JSON.stringify({ audio: b64 }));
                    }
                } catch (e) {
                    // Swallow to avoid audio glitching; logs will show errors
                }
            }
        };

        if (!analysisCanvas) {
            analysisCanvas = document.createElement('canvas');
            analysisCanvas.width = 160;
            analysisCanvas.height = 120;
            analysisCtx2d = analysisCanvas.getContext('2d', { willReadFrequently: true });
        }

        if (!USE_WS_ANALYSIS) {
            analysisTimer = setInterval(analyzeAndSend, 2000);
        }

        if (USE_WS_ANALYSIS) {
            connectWSAnalyze();
        }

        // Immediately start with an opening joke (no need to wait for first reaction)
        try {
            jokeInFlight = true;
            lastJokeTs = Date.now();
            const opening = { verdict: 'uncertain', rationale: 'opening turn', ts: new Date().toISOString() };
            const joke_id = ++jokeSeq; activeJokeId = joke_id;
            fetch(`${JOKE_API_BASE}/generate/from_analysis?include_audio=true`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...opening, joke_id })
            })
                .then(r => r.json())
                .then(j => {
                    if (j && j.joke_id !== activeJokeId) return;
                    if (j && j.text) addLog('agent', j.text, 'info');
                    if (j && j.audio_base64) enqueueAgentOutput(null, j.audio_base64, 24000);
                    if (j && j.text) {
                        lastJokeText = j.text;
                        lastJokeAt = Date.now();
                        timelineEvents.push({ type: 'joke', ts: lastJokeAt, text: j.text, joke_id: j.joke_id });
                        if (timelineEvents.length > 500) timelineEvents.shift();
                    }
                })
                .catch(() => {})
                .finally(() => { jokeInFlight = false; scheduleFallback(); });
        } catch (_) {}

        // Start periodic visual analysis (every ~3s)
        try {
            if (visualTimer) clearInterval(visualTimer);
            visualTimer = setInterval(async () => {
                if (!sessionRunning) return;
                if (!analysisCanvas || !analysisCtx2d || !cameraPreview || cameraPreview.readyState < 2) return;
                try {
                    analysisCtx2d.drawImage(cameraPreview, 0, 0, analysisCanvas.width, analysisCanvas.height);
                    const dataUrl = analysisCanvas.toDataURL('image/jpeg', 0.7);
                    const imageBase64 = dataUrl.split(',')[1];
                    const res = await fetch(`${OPENAI_COMPAT_API_BASE}/analyze-image`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image_base64: imageBase64 })
                    });
                    if (res.ok) {
                        const v = await res.json();
                        addLog('visual', `Verdict: ${v.visual_verdict} (conf ${Math.round(v.confidence*100)}%)`, 'info');
                        latestVisualAnalysis = v;
                        timelineEvents.push({ type: 'visual', ts: Date.now(), payload: v });
                        if (timelineEvents.length > 500) timelineEvents.shift();
                        try { pushReaction('visual', v.visual_verdict, (v.confidence!=null ? v.confidence*100 : null), Date.now()); } catch(_){}
                    }
                } catch (_) {}
            }, 3000);
        } catch (_) {}

        sessionRunning = true;
        startBtn && (startBtn.textContent = 'Stop');
        sessionStatus && (sessionStatus.textContent = 'Running');
        micStatus && (micStatus.textContent = 'Listening...');
        micDot && micDot.classList.add('on');
        statusText && (statusText.textContent = 'Session running');
        addLog('system', 'Session started', 'success');
    } catch (err) {
        addLog('system', `Permission or device error: ${err.message}`, 'error');
        statusText && (statusText.textContent = 'Permission denied or unavailable');
    }
}

async function stopSession() {
    if (!sessionRunning) return;
    try {
        if (analysisTimer) clearInterval(analysisTimer);
        if (fallbackTimeout) { clearTimeout(fallbackTimeout); fallbackTimeout = null; }
        if (visualTimer) { clearInterval(visualTimer); visualTimer = null; }
        if (wsAnalyze) { try { wsAnalyze.close(); } catch (_) {} wsAnalyze = null; }
        try { if (currentAudioEl) { currentAudioEl.pause(); } } catch (_) {}
        currentAudioEl = null;
        audioPlaying = false;
        speechQueue = [];
        drainingSpeechQueue = false;
        if (processorNode) processorNode.disconnect();
        if (sourceNode) sourceNode.disconnect();
        if (audioCtx) await audioCtx.close();
        if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    } finally {
        analysisTimer = null; audioCtx = null; mediaStream = null; sourceNode = null; processorNode = null; lastAudioRms = 0;
        updateMicLevel(0);
        startBtn && (startBtn.textContent = 'Start');
        sessionStatus && (sessionStatus.textContent = 'Idle');
        micStatus && (micStatus.textContent = 'Idle');
        micDot && micDot.classList.remove('on');
        statusText && (statusText.textContent = 'Ready');
        sessionRunning = false;
        addLog('system', 'Session stopped', 'warning');
    }
}

if (startBtn) startBtn.onclick = async () => { if (!sessionRunning) await startSession(); else await stopSession(); };

function getAverageBrightness(videoEl) {
    if (!videoEl || !analysisCtx2d || videoEl.readyState < 2) return 0;
    analysisCtx2d.drawImage(videoEl, 0, 0, analysisCanvas.width, analysisCanvas.height);
    const { data } = analysisCtx2d.getImageData(0, 0, analysisCanvas.width, analysisCanvas.height);
    let total = 0; let count = 0;
    for (let i = 0; i < data.length; i += 16) { // sample every 4th pixel
        const r = data[i], g = data[i + 1], b = data[i + 2];
        total += (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
        count++;
    }
    return count ? total / count : 0;
}

function classifyReaction(rms, brightness) {
    if (rms > 0.12) return 'clapping';
    if (rms > 0.06 && brightness > 0.25) return 'laughing';
    if (rms < 0.02) return 'silent';
    return 'neutral';
}

async function analyzeAndSend() {
    if (USE_WS_ANALYSIS) return; // disabled when using WS streaming
    const brightness = getAverageBrightness(cameraPreview);
    const reaction = classifyReaction(lastAudioRms, brightness);
    const payload = {
        reaction_type: reaction,
        audio_rms: Number(lastAudioRms.toFixed(4)),
        video_brightness: Number(brightness.toFixed(3)),
        ts: new Date().toISOString()
    };

    try {
        const res = await sendAnalysisToAPI(payload);
        const conf = Math.round((res.confidence || 0.75) * 100);
        micStatus && (micStatus.textContent = `Last: ${reaction} (${conf}%)`);
        addLog('analyzer', `Reaction: ${reaction} (conf ${conf}%) | rms ${payload.audio_rms} | b ${payload.video_brightness}`, 'info');
    } catch (err) {
        addLog('analyzer', `Send failed: ${err.message}`, 'error');
    }
}

async function sendAnalysisToAPI(payload) {
    if (!USE_MOCK_API) {
        const url = `${OPENAI_COMPAT_API_BASE}/analyze`;
        const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }
    return await new Promise((resolve) => {
        setTimeout(() => {
            resolve({ reaction_type: payload.reaction_type, confidence: 0.6 + Math.random() * 0.4 });
        }, 150);
    });
}

// WebSocket: connect to audience analyzer stream
function connectWSAnalyze() {
    const wsUrl = OPENAI_COMPAT_API_BASE.replace(/^http/, 'ws') + '/ws/analyze';
    try {
        wsAnalyze = new WebSocket(wsUrl);
        wsAnalyze.onopen = () => {
            addLog('analyzer', 'WS connected to /ws/analyze', 'success');
            statusText && (statusText.textContent = 'Streaming audio to analyzer');
        };
        wsAnalyze.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                const verdict = msg.verdict;
                const reaction = msg.reaction_type || verdict || 'unknown';
                const hasConf = typeof msg.confidence === 'number';
                const confPct = hasConf ? ` (${Math.round(msg.confidence * 100)}%)` : '';
                micStatus && (micStatus.textContent = `Last: ${reaction}${confPct}`);
                addLog('analyzer', verdict ? `WS: ${verdict}${confPct}` : `WS: ${reaction}${confPct}`, 'info');
                // cache latest analysis and attempt immediate trigger if we're ready
                latestAudioAnalysis = msg;
                // push to reaction plot (audio)
                try { pushReaction('audio', reaction, hasConf ? (msg.confidence * 100) : null, Date.now()); } catch(_){}
            } catch (e) {
                addLog('analyzer', `WS parse: ${e.message}`, 'warning');
            }
        };
        wsAnalyze.onerror = () => {
            addLog('analyzer', 'WS error', 'error');
        };
        wsAnalyze.onclose = () => {
            addLog('analyzer', 'WS closed', 'warning');
            if (sessionRunning) setTimeout(connectWSAnalyze, 1500);
        };
    } catch (e) {
        addLog('analyzer', `WS connect failed: ${e.message}`, 'error');
    }
}

// Resample float32 to 16k PCM16, maintaining state across calls
function resampleTo16kPCM16(inputFloat32, inSampleRate, state) {
    const concatLen = state.tail.length + inputFloat32.length;
    const samples = new Float32Array(concatLen);
    samples.set(state.tail, 0);
    samples.set(inputFloat32, state.tail.length);

    const ratio = inSampleRate / TARGET_SR;
    const avail = samples.length - state.t; // effective samples from current fractional offset
    const outLength = Math.max(0, Math.floor(avail / ratio));
    const out = new Int16Array(outLength);
    let o = 0;
    for (let n = 0; n < outLength; n++) {
        const idx = Math.floor(state.t + n * ratio);
        const s = samples[idx] || 0;
        const clamped = Math.max(-1, Math.min(1, s));
        out[o++] = (clamped * 32767) | 0;
    }
    // compute new fractional position and tail
    const consumed = Math.floor(state.t + outLength * ratio);
    const newT = (state.t + outLength * ratio) - consumed; // fractional carry
    const newTail = samples.subarray(consumed);
    return { out, state: { tail: newTail, t: newT } };
}

function u8ToBase64(u8) {
    const CHUNK = 0x8000;
    let binary = '';
    for (let i = 0; i < u8.length; i += CHUNK) {
        binary += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK));
    }
    return btoa(binary);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function triggerIfReady(analysis = null) {
    if (!sessionRunning) return false;
    const now = Date.now();
    if (audioPlaying || speechQueue.length > 0 || jokeInFlight) return false;
    // Ensure there's a beat after the last speaking turn
    const sinceEnd = now - (lastJokeEndAt || lastJokeTs || 0);
    if (sinceEnd < MIN_MESSAGE_GAP_MS) return false;
    // Respect minimal cooldown between generations
    if ((now - lastJokeTs) < JOKE_COOLDOWN_MS) return false;
    const chosen = analysis || latestAudioAnalysis || { verdict: 'uncertain', rationale: 'no recent analysis' };
    maybeTriggerJoke(chosen);
    return true;
}

// Audio helpers: wrap PCM16 24k mono into WAV for playback
function pcm16ToWavBytes(pcmBytes, sampleRate = 24000, numChannels = 1) {
    const blockAlign = numChannels * 2;
    const byteRate = sampleRate * blockAlign;
    const dataSize = pcmBytes.length;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);
    let p = 0;
    function writeStr(s) { for (let i = 0; i < s.length; i++) view.setUint8(p++, s.charCodeAt(i)); }
    function write32(v) { view.setUint32(p, v, true); p += 4; }
    function write16(v) { view.setUint16(p, v, true); p += 2; }
    writeStr('RIFF');
    write32(36 + dataSize);
    writeStr('WAVE');
    writeStr('fmt ');
    write32(16);
    write16(1);
    write16(numChannels);
    write32(sampleRate);
    write32(byteRate);
    write16(blockAlign);
    write16(16);
    writeStr('data');
    write32(dataSize);
    new Uint8Array(buffer, 44).set(pcmBytes);
    return new Uint8Array(buffer);
}

async function playPcm16Base64(b64, sampleRate = 24000) {
    return await new Promise((resolve) => {
        try {
            const pcmBytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const wavBytes = pcm16ToWavBytes(pcmBytes, sampleRate, 1);
            const blob = new Blob([wavBytes], { type: 'audio/wav' });
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            currentAudioEl = audio;
            audioPlaying = true;
            const cleanup = () => {
                audio.onended = null;
                audio.onerror = null;
                if (currentAudioEl === audio) currentAudioEl = null;
                audioPlaying = false;
                try { URL.revokeObjectURL(url); } catch (_) {}
            };
            audio.onended = () => { lastJokeEndAt = Date.now(); cleanup(); resolve(); try { triggerIfReady(); } catch (_) {} };
            audio.onerror = () => { cleanup(); resolve(); };
            audio.play().catch(() => { cleanup(); resolve(); });
            setTimeout(() => { lastJokeEndAt = Date.now(); cleanup(); resolve(); try { triggerIfReady(); } catch (_) {} }, 15000);
        } catch (_) { resolve(); }
    });
}

function enqueueAgentOutput(text, audioBase64, sampleRate = 24000) {
    speechQueue.push({ text, audioBase64, sampleRate });
    if (!drainingSpeechQueue) drainSpeechQueue();
}

async function drainSpeechQueue() {
    if (drainingSpeechQueue) return;
    drainingSpeechQueue = true;
    try {
        while (speechQueue.length && sessionRunning) {
            const { text, audioBase64, sampleRate } = speechQueue.shift();
            const now = Date.now();
            const gap = now - lastSpokenAt;
            if (gap < MIN_MESSAGE_GAP_MS) await sleep(MIN_MESSAGE_GAP_MS - gap);
            if (text) addLog('agent', text, 'info');
            if (audioBase64) {
                await playPcm16Base64(audioBase64, sampleRate);
                await sleep(POST_TTS_DELAY_MS);
            } else {
                await sleep(Math.max(MIN_MESSAGE_GAP_MS, POST_TTS_DELAY_MS));
            }
            lastSpokenAt = Date.now();
        }
    } finally {
        drainingSpeechQueue = false;
    }
}

function verdictToLabel(verdict) {
    if (verdict === 'hit') return 'big laugh / applause';
    if (verdict === 'mixed') return 'small laugh / chatter';
    if (verdict === 'miss') return 'silence / groan';
    if (verdict === 'uncertain') return 'confusion';
    return 'neutral';
}

// Win95-styled rendering for reaction logs
function maybeRenderWin95Reaction(service, message) {
    // Keep system boring
    if (service === 'system') return escapeHtml(message);

    // Only style audience / visual / analyzer
    const svc = String(service || '').toLowerCase();
    if (!/(audience|visual|analyzer)/.test(svc)) return escapeHtml(message);

    const parsed = parseReactionMessage(message);
    if (!parsed) return escapeHtml(message);

    const { source, verdict, confidencePct, raw } = parsed;
    const v = String((verdict || '').toLowerCase());
    const cls = verdictClass(v);
    const icon = verdictIcon(v);
    const conf = Number.isFinite(confidencePct) ? Math.max(0, Math.min(100, Math.round(confidencePct))) : null;

    const meter = conf == null ? '' : `
        <div class="meter-95" aria-label="confidence">
            <div class="meter-95-bar" style="width:${conf}%"></div>
        </div>`;

    return `
        <div class="reaction-95">
            <span class="badge-95 ${cls}"><span class="badge-95-icon">${icon}</span>${escapeHtml(v || source)}</span>
            ${conf == null ? '' : `<span class="conf-label">${conf}%</span>`}
            ${meter}
            <span class="reaction-src">${escapeHtml(source || svc)}</span>
        </div>
    `;
}

function parseReactionMessage(message) {
    const text = String(message || '');
    // Patterns we emit in the app:
    //  - "Verdict: laughing (conf 90%)"
    //  - "Visual: neutral (conf 0.85)" (fraction)
    //  - "WS: hit (90%)" or "WS: miss"
    let m;
    // Verdict: X (conf 90%)
    m = text.match(/Verdict:\s*(\w+)\s*\(conf\s*(\d+)%\)/i);
    if (m) return { source: 'visual', verdict: m[1], confidencePct: Number(m[2]), raw: text };

    // Visual: X (conf 0.85)
    m = text.match(/Visual:\s*(\w+)\s*\(conf\s*([0-9.]+)\)/i);
    if (m) {
        const frac = parseFloat(m[2]);
        return { source: 'visual', verdict: m[1], confidencePct: Number.isFinite(frac) ? frac * 100 : null, raw: text };
    }

    // WS: verdict (90%) or WS: verdict
    m = text.match(/WS:\s*(\w+)(?:\s*\((\d+)%\))?/i);
    if (m) {
        const pct = m[2] ? Number(m[2]) : null;
        return { source: 'audio', verdict: m[1], confidencePct: pct, raw: text };
    }

    return null;
}

function verdictClass(v) {
    if (v === 'laughing' || v === 'hit') return 'is-positive';
    if (v === 'enjoying' || v === 'mixed') return 'is-warm';
    if (v === 'neutral') return 'is-neutral';
    if (v === 'miss' || v === 'silent' || v === 'silence') return 'is-negative';
    if (v === 'uncertain' || v === 'unknown') return 'is-unknown';
    return 'is-neutral';
}

function verdictIcon(v) {
    if (v === 'laughing' || v === 'hit') return '☺';
    if (v === 'enjoying' || v === 'mixed') return '♬';
    if (v === 'neutral') return '◼';
    if (v === 'miss' || v === 'silent' || v === 'silence') return '✖';
    if (v === 'uncertain' || v === 'unknown') return '¿';
    return '◻';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Reaction plot utilities
function pushReaction(source, verdict, confidencePct, ts) {
    reactionSeries.push({ ts, source, verdict: String(verdict || '').toLowerCase(), confidencePct: confidencePct == null ? null : Math.max(0, Math.min(100, Math.round(confidencePct))) });
    // Trim old points periodically
    const cutoff = Date.now() - REACTION_WINDOW_MS * 2;
    if (reactionSeries.length > 1000) reactionSeries = reactionSeries.filter(p => p.ts >= cutoff);
}

function colorForVerdict(v) {
    if (v === 'laughing' || v === 'hit') return '#178a17'; // green
    if (v === 'enjoying' || v === 'mixed') return '#b36b00'; // warm
    if (v === 'neutral') return '#666666'; // gray
    if (v === 'miss' || v === 'silent' || v === 'silence') return '#a11a1a'; // red
    if (v === 'uncertain' || v === 'unknown') return '#5a4da3'; // purple
    return '#666666';
}

function yForVerdict(v, h) {
    // 5 bands (0..4) from bottom to top
    const map = {
        'miss': 0, 'silent': 0, 'silence': 0,
        'uncertain': 1, 'unknown': 1,
        'neutral': 2,
        'enjoying': 3, 'mixed': 3,
        'laughing': 4, 'hit': 4,
    };
    const band = map[v] != null ? map[v] : 2;
    const rows = 5;
    const pad = 8;
    const bandHeight = Math.max(1, (h - pad * 2) / (rows - 1));
    return Math.round(h - pad - band * bandHeight);
}

function renderReactionPlot() {
    if (!reactionCanvas || !reactionCtx) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const cssW = reactionCanvas.clientWidth || 300;
    const cssH = reactionCanvas.clientHeight || 96;
    const needResize = reactionCanvas.width !== Math.floor(cssW * dpr) || reactionCanvas.height !== Math.floor(cssH * dpr);
    if (needResize) {
        reactionCanvas.width = Math.floor(cssW * dpr);
        reactionCanvas.height = Math.floor(cssH * dpr);
        reactionCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    const ctx = reactionCtx;
    const w = cssW, h = cssH;
    // background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
    // inner border
    ctx.strokeStyle = '#808080';
    ctx.strokeRect(0.5, 0.5, w - 1, h - 1);

    const now = Date.now();
    const windowMs = REACTION_WINDOW_MS;
    // grid bands
    ctx.strokeStyle = '#e0e0e0';
    for (let i = 0; i < 5; i++) {
        const y = yForVerdict(['miss','uncertain','neutral','enjoying','laughing'][i], h);
        ctx.beginPath();
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(w, y + 0.5);
        ctx.stroke();
    }

    // draw points
    const points = reactionSeries.filter(p => p.ts >= now - windowMs);
    const leftPad = 6, rightPad = 2;
    for (const p of points) {
        const x = leftPad + ((p.ts - (now - windowMs)) / windowMs) * (w - leftPad - rightPad);
        const y = yForVerdict(p.verdict, h);
        const color = colorForVerdict(p.verdict);
        const alpha = p.confidencePct == null ? 0.8 : (0.4 + 0.6 * (p.confidencePct / 100));
        ctx.globalAlpha = alpha;
        ctx.fillStyle = color;
        ctx.strokeStyle = '#000000';

        if (p.source === 'visual') {
            const s = 6; // square
            ctx.fillRect(x - s/2, y - s/2, s, s);
            ctx.globalAlpha = 1.0;
            ctx.strokeRect(x - s/2, y - s/2, s, s);
        } else {
            const r = 3.5; // audio circle
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 1.0;
            ctx.stroke();
        }
    }

    // now marker
    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = '#b0b0b0';
    ctx.beginPath();
    ctx.moveTo(w - rightPad - 0.5, 0);
    ctx.lineTo(w - rightPad - 0.5, h);
    ctx.stroke();

    reactionAnimationHandle = requestAnimationFrame(renderReactionPlot);
}

function initReactionPlot() {
    reactionCanvas = document.getElementById('reaction-canvas');
    if (!reactionCanvas) return;
    reactionCtx = reactionCanvas.getContext('2d');
    if (reactionAnimationHandle) cancelAnimationFrame(reactionAnimationHandle);
    renderReactionPlot();
    window.addEventListener('resize', () => { if (reactionCanvas) renderReactionPlot(); });
}

function summarizeWindow(tsFromMs, tsToMs = Date.now()) {
    const win = timelineEvents
        .filter(e => e.ts >= tsFromMs && e.ts <= tsToMs)
        .sort((a,b)=>a.ts-b.ts);
    const audioCounts = {};
    const visualCounts = {};
    for (const e of win) {
        if (e.type === 'audio') {
            const v = (e.payload && (e.payload.verdict || e.payload.reaction_type)) || 'unknown';
            audioCounts[v] = (audioCounts[v] || 0) + 1;
        } else if (e.type === 'visual') {
            const v = (e.payload && e.payload.visual_verdict) || 'unknown';
            visualCounts[v] = (visualCounts[v] || 0) + 1;
        }
    }
    return { audio_counts: audioCounts, visual_counts: visualCounts, window_ms: tsToMs - tsFromMs };
}

function fuseReactions(audio_latest, visual_latest) {
    const aVerdict = audio_latest && (audio_latest.verdict || audio_latest.reaction_type);
    const vVerdict = visual_latest && visual_latest.visual_verdict;
    if (vVerdict === 'laughing') return 'big laugh / applause';
    if (aVerdict === 'hit') return 'big laugh / applause';
    if (vVerdict === 'enjoying') return 'small laugh / chatter';
    if (aVerdict === 'mixed') return 'small laugh / chatter';
    if (aVerdict === 'miss') return 'silence / groan';
    if (aVerdict === 'uncertain' || vVerdict === 'uncertain') return 'confusion';
    return 'neutral';
}

function buildJokeContext(baseAnalysis) {
    // Build a compact, non-duplicative tail, ordered by timestamp
    const tailRaw = timelineEvents.slice(-50).sort((a,b)=>a.ts-b.ts);
    const audio_latest = latestAudioAnalysis || null;
    const visual_latest = latestVisualAnalysis || null;
    const fused_reaction = fuseReactions(audio_latest, visual_latest);
    const latestAudioTs = audio_latest && audio_latest.timestamp ? Date.parse(audio_latest.timestamp) : null;
    const latestVisualTs = visual_latest && visual_latest.timestamp ? Date.parse(visual_latest.timestamp) : null;

    const tail = tailRaw
        .filter(e => {
            // Drop current prev_joke duplicate in tail
            if (e.type === 'joke' && e.ts === lastJokeAt) return false;
            // Avoid duplicating latest audio/visual already broken out
            if (e.type === 'audio' && latestAudioTs && Math.abs(e.ts - latestAudioTs) < 5) return false;
            if (e.type === 'visual' && latestVisualTs && Math.abs(e.ts - latestVisualTs) < 5) return false;
            return true;
        })
        .map(e => {
            if (e.type === 'visual') {
                const v = e.payload || {};
                return { type: 'visual', ts: e.ts, visual_verdict: v.visual_verdict, confidence: v.confidence };
            }
            if (e.type === 'audio') {
                const v = e.payload || {};
                return { type: 'audio', ts: e.ts, verdict: v.verdict || v.reaction_type };
            }
            if (e.type === 'joke') {
                return { type: 'joke', ts: e.ts, joke_id: e.joke_id };
            }
            return e;
        })
        .slice(-12);
    // Window summaries around the last joke
    const pre_window = lastJokeAt ? summarizeWindow(Math.max(0, lastJokeAt - 3000), lastJokeAt) : null;
    const during_window = (lastJokeAt && lastJokeEndAt && lastJokeEndAt > lastJokeAt)
        ? summarizeWindow(lastJokeAt, lastJokeEndAt) : null;
    const post_window = (lastJokeEndAt && lastJokeEndAt <= Date.now())
        ? summarizeWindow(lastJokeEndAt, Date.now()) : null;

    return {
        prev_joke: lastJokeText ? { text: lastJokeText, ts_start: lastJokeAt, ts_end: lastJokeEndAt || null } : null,
        fused_reaction,
        audio_latest,
        visual_latest,
        windows: { pre_window, during_window, post_window },
        timeline_tail: tail,
        analysis: baseAnalysis || null
    };
}

function maybeTriggerJoke(analysis) {
    const now = Date.now();
    if (audioPlaying || speechQueue.length > 0 || jokeInFlight || (now - lastJokeTs) < JOKE_COOLDOWN_MS) return;
    jokeInFlight = true;
    lastJokeTs = Date.now();
    const includeAudio = true;
    const joke_id = ++jokeSeq; activeJokeId = joke_id;
    const contextPayload = buildJokeContext(analysis);
    const payload = { joke_id, context: contextPayload };
    if (DEBUG_CONTEXT) {
        try { fetch(`${JOKE_API_BASE}/debug/context`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) }).catch(()=>{}); } catch(_){}
    }
    fetch(`${JOKE_API_BASE}/generate/from_analysis?include_audio=${includeAudio}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(async j => {
            if (j && j.joke_id !== activeJokeId) return;
            if (j && j.text) addLog('agent', j.text, 'info');
            if (j && j.audio_base64) enqueueAgentOutput(null, j.audio_base64, 24000);
            if (DEBUG_CONTEXT) {
                try { fetch(`${JOKE_API_BASE}/debug/context`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ response_joke_id: j && j.joke_id }) }).catch(()=>{}); } catch(_){}
            }
            if (j && j.text) {
                lastJokeText = j.text;
                lastJokeAt = Date.now();
                timelineEvents.push({ type: 'joke', ts: lastJokeAt, text: j.text, joke_id: j.joke_id });
                if (timelineEvents.length > 500) timelineEvents.shift();
            }
        })
        .catch(() => {})
        .finally(() => { lastJokeTs = Date.now(); jokeInFlight = false; scheduleFallback(); });
}

function scheduleFallback() {
    if (fallbackTimeout) { clearTimeout(fallbackTimeout); fallbackTimeout = null; }
    if (!sessionRunning) return;
    const baseTime = lastJokeEndAt || lastJokeTs;
    const delay = Math.max(500, JOKE_FALLBACK_MS - (Date.now() - baseTime));
    fallbackTimeout = setTimeout(() => {
        if (!sessionRunning) return;
        if (audioPlaying || speechQueue.length > 0 || jokeInFlight) return scheduleFallback();
        const synthetic = { verdict: 'uncertain', rationale: 'no reaction yet', ts: new Date().toISOString() };
        jokeInFlight = true;
        lastJokeTs = Date.now();
        const joke_id = ++jokeSeq; activeJokeId = joke_id;
        const contextPayload = buildJokeContext(synthetic);
        const payload = { joke_id, context: contextPayload };
        if (DEBUG_CONTEXT) {
            try { fetch(`${JOKE_API_BASE}/debug/context`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) }).catch(()=>{}); } catch(_){}
        }
        fetch(`${JOKE_API_BASE}/generate/from_analysis?include_audio=true`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        })
            .then(r => r.json())
        .then(async j => {
                if (j && j.joke_id !== activeJokeId) return;
                if (j && j.text) addLog('agent', j.text, 'info');
                if (j && j.audio_base64) enqueueAgentOutput(null, j.audio_base64, 24000);
                if (DEBUG_CONTEXT) {
                    try { fetch(`${JOKE_API_BASE}/debug/context`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ response_joke_id: j && j.joke_id }) }).catch(()=>{}); } catch(_){}
                }
                if (j && j.text) {
                    lastJokeText = j.text;
                    lastJokeAt = Date.now();
                    timelineEvents.push({ type: 'joke', ts: lastJokeAt, text: j.text, joke_id: j.joke_id });
                    if (timelineEvents.length > 500) timelineEvents.shift();
                }
            })
            .catch(() => {})
            .finally(() => { jokeInFlight = false; scheduleFallback(); });
    }, delay);
}

// Initial log
addLog('system', 'Cringe Reinforcement Learning UI initialized', 'success');

// DVD-style bouncing "CringeGPT" screensaver (under main window)
(function initDvdScreensaver() {
    const layer = document.getElementById('dvd-layer');
    const logo = document.getElementById('dvd-logo');
    if (!layer || !logo) return;

    let bounds = layer.getBoundingClientRect();
    let logoWidth = 0;
    let logoHeight = 0;
    let x = Math.random() * Math.max(1, bounds.width - 120);
    let y = Math.random() * Math.max(1, bounds.height - 60);
    let vx = 180; // px/s
    let vy = 150; // px/s
    let lastTs = null;

    function setRandomColor() {
        const hue = Math.floor(Math.random() * 360);
        const sat = 85;
        const light = 60;
        logo.style.color = `hsl(${hue} ${sat}% ${light}%)`;
    }

    function measure() {
        // Force measurement by temporarily showing transform
        logo.style.transform = `translate3d(-9999px, -9999px, 0)`;
        logoWidth = logo.offsetWidth;
        logoHeight = logo.offsetHeight;
    }

    function clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

    function step(ts) {
        if (lastTs == null) lastTs = ts;
        const dt = Math.min(0.050, (ts - lastTs) / 1000); // cap delta to avoid jumps
        lastTs = ts;

        const maxX = Math.max(0, bounds.width - logoWidth);
        const maxY = Math.max(0, bounds.height - logoHeight);

        x += vx * dt;
        y += vy * dt;

        let bounced = false;
        if (x <= 0) { x = 0; vx = Math.abs(vx); bounced = true; }
        else if (x >= maxX) { x = maxX; vx = -Math.abs(vx); bounced = true; }

        if (y <= 0) { y = 0; vy = Math.abs(vy); bounced = true; }
        else if (y >= maxY) { y = maxY; vy = -Math.abs(vy); bounced = true; }

        if (bounced) setRandomColor();
        logo.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        requestAnimationFrame(step);
    }

    function handleResize() {
        bounds = layer.getBoundingClientRect();
        measure();
        x = clamp(x, 0, Math.max(0, bounds.width - logoWidth));
        y = clamp(y, 0, Math.max(0, bounds.height - logoHeight));
    }

    // Initialize
    measure();
    setRandomColor();
    handleResize();
    window.addEventListener('resize', handleResize);
    requestAnimationFrame(step);
})();
