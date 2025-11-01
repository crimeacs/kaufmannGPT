// Configuration (mocked OpenAI-compatible pipeline by default)
const USE_MOCK_API = true;
const OPENAI_COMPAT_API_BASE = 'http://localhost:8000/v1';

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
        <div class="message">${message}</div>
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
        };

        if (!analysisCanvas) {
            analysisCanvas = document.createElement('canvas');
            analysisCanvas.width = 160;
            analysisCanvas.height = 120;
            analysisCtx2d = analysisCanvas.getContext('2d', { willReadFrequently: true });
        }

        analysisTimer = setInterval(analyzeAndSend, 2000);

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

// Initial log
addLog('system', 'Cringe-based Reinforcement Learning UI initialized', 'success');
