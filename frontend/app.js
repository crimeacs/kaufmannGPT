// Configuration
const AUDIENCE_SERVICE_URL = 'http://localhost:8002';
const JOKE_SERVICE_URL = 'http://localhost:8003';

// State
let autoScrollEnabled = true;
let autoModeRunning = false;
let autoModeInterval = null;
let listening = false;
let audioCtx = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let ws = null;
let lastSent = 0;

// Modal
const modal = document.getElementById('response-modal');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const modalClose = document.querySelector('.modal-close');
const modalCopy = document.getElementById('modal-copy');

function showModal(title, content) {
    modalTitle.textContent = title;
    modalBody.textContent = JSON.stringify(content, null, 2);
    modal.classList.add('show');
}

function hideModal() {
    modal.classList.remove('show');
}

modalClose.onclick = hideModal;
window.onclick = (e) => {
    if (e.target === modal) hideModal();
};

modalCopy.onclick = () => {
    navigator.clipboard.writeText(modalBody.textContent);
    modalCopy.textContent = 'Copied!';
    setTimeout(() => {
        modalCopy.textContent = 'Copy to Clipboard';
    }, 2000);
};

// Logging
const logsContainer = document.getElementById('logs-container');

function addLog(service, message, level = 'info') {
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

    if (autoScrollEnabled) {
        entry.scrollIntoView({ behavior: 'smooth' });
    }

    // Keep only last 200 logs
    while (logsContainer.children.length > 200) {
        logsContainer.removeChild(logsContainer.firstChild);
    }
}

document.getElementById('clear-logs').onclick = () => {
    logsContainer.innerHTML = '';
    addLog('system', 'Logs cleared', 'info');
};

document.getElementById('toggle-autoscroll').onclick = (e) => {
    autoScrollEnabled = !autoScrollEnabled;
    e.target.textContent = `Auto-scroll: ${autoScrollEnabled ? 'ON' : 'OFF'}`;
};

// Health checks
async function checkHealth(url, statusElementId, serviceName) {
    try {
        const response = await fetch(`${url}/health`);
        const statusDot = document.getElementById(statusElementId);

        if (response.ok) {
            statusDot.classList.add('online');
            statusDot.classList.remove('offline');
            return true;
        } else {
            throw new Error(`Status: ${response.status}`);
        }
    } catch (error) {
        const statusDot = document.getElementById(statusElementId);
        statusDot.classList.add('offline');
        statusDot.classList.remove('online');
        addLog('system', `${serviceName} is offline: ${error.message}`, 'error');
        return false;
    }
}

// Start health checks
setInterval(() => {
    checkHealth(AUDIENCE_SERVICE_URL, 'audience-status', 'Audience Service');
    checkHealth(JOKE_SERVICE_URL, 'joke-status', 'Joke Service');
}, 5000);

// Initial check
checkHealth(AUDIENCE_SERVICE_URL, 'audience-status', 'Audience Service');
checkHealth(JOKE_SERVICE_URL, 'joke-status', 'Joke Service');

// SSE Log Streaming
function connectLogStream(url, serviceName) {
    addLog('system', `Connecting to ${serviceName} log stream...`, 'info');

    const eventSource = new EventSource(`${url}/stream/logs`);

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            addLog(data.service || serviceName, data.message, data.level || 'info');
        } catch (error) {
            console.error('Error parsing log:', error);
        }
    };

    eventSource.onerror = (error) => {
        addLog('system', `${serviceName} log stream disconnected`, 'warning');
        eventSource.close();

        // Reconnect after 5 seconds
        setTimeout(() => {
            addLog('system', `Reconnecting to ${serviceName} log stream...`, 'info');
            connectLogStream(url, serviceName);
        }, 5000);
    };

    return eventSource;
}

// Connect to log streams
connectLogStream(AUDIENCE_SERVICE_URL, 'audience');
connectLogStream(JOKE_SERVICE_URL, 'joke');

// Helpers
function httpToWs(url) {
    try {
        const u = new URL(url);
        u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
        return u.toString();
    } catch {
        return url.replace('https://', 'wss://').replace('http://', 'ws://');
    }
}

async function parseJsonResponse(response) {
    let data;
    try {
        data = await response.json();
    } catch (e) {
        throw new Error(`HTTP ${response.status}`);
    }
    if (!response.ok) {
        const err = data && data.error ? data.error : { code: 'HTTP_ERROR', message: `HTTP ${response.status}` };
        throw new Error(`${err.code}: ${err.message}`);
    }
    if (data && data.error) {
        const err = data.error;
        throw new Error(`${err.code}: ${err.message}`);
    }
    return data;
}

// Audio utils
function downsampleBuffer(buffer, sampleRate, outSampleRate) {
    if (outSampleRate === sampleRate) return buffer;
    const ratio = sampleRate / outSampleRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < newLen) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        // Simple average to low-pass a bit
        let accum = 0, count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        result[offsetResult] = accum / (count || 1);
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}

function floatTo16BitPCM(floatBuf) {
    const out = new Int16Array(floatBuf.length);
    for (let i = 0; i < floatBuf.length; i++) {
        let s = Math.max(-1, Math.min(1, floatBuf[i]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return out.buffer;
}

function bufToBase64(buf) {
    const bytes = new Uint8Array(buf);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
}

function updateMicLevel(level) {
    const lvl = Math.max(0, Math.min(1, level));
    const pct = Math.round(lvl * 100);
    const bar = document.getElementById('mic-level');
    if (bar) bar.style.width = pct + '%';
}

async function startListening() {
    if (listening) return;
    try {
        const wsUrl = httpToWs(AUDIENCE_SERVICE_URL) + '/ws/analyze';
        ws = new WebSocket(wsUrl);
        ws.onopen = () => addLog('audience', 'Listening WS connected', 'success');
        ws.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                if (data.error) {
                    addLog('audience', `Analyzer error: ${data.error.code}: ${data.error.message}`, 'error');
                } else if (data.reaction_type) {
                    addLog('audience', `Live analysis: ${data.reaction_type} (conf ${Math.round((data.confidence||0)*100)}%)`, 'info');
                }
            } catch {}
        };
        ws.onerror = () => addLog('audience', 'Listening WS error', 'error');
        ws.onclose = () => addLog('audience', 'Listening WS closed', 'warning');

        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        sourceNode = audioCtx.createMediaStreamSource(mediaStream);
        const bufferSize = 2048;
        processorNode = audioCtx.createScriptProcessor(bufferSize, 1, 1);
        sourceNode.connect(processorNode);
        processorNode.connect(audioCtx.destination);

        processorNode.onaudioprocess = (e) => {
            const input = e.inputBuffer.getChannelData(0);
            // RMS for mic level
            let sum = 0;
            for (let i = 0; i < input.length; i++) sum += input[i]*input[i];
            updateMicLevel(Math.sqrt(sum / input.length));

            if (!ws || ws.readyState !== 1) return;
            const now = Date.now();
            if (now - lastSent < 400) return; // throttle ~2.5 msgs/sec
            const down = downsampleBuffer(input, audioCtx.sampleRate, 16000);
            const pcm16 = floatTo16BitPCM(down);
            const b64 = bufToBase64(pcm16);
            ws.send(JSON.stringify({ audio: b64 }));
            lastSent = now;
        };

        listening = true;
        document.getElementById('toggle-listening').textContent = 'Stop Listening';
        document.getElementById('toggle-listening').classList.add('listening');
        document.getElementById('mic-status').textContent = 'Listening...';
        addLog('system', 'Listening mode started', 'success');
    } catch (err) {
        addLog('audience', `Failed to start listening: ${err.message}`, 'error');
    }
}

async function stopListening() {
    if (!listening) return;
    try {
        if (processorNode) processorNode.disconnect();
        if (sourceNode) sourceNode.disconnect();
        if (audioCtx) await audioCtx.close();
        if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
        if (ws) try { ws.close(); } catch {}
    } finally {
        audioCtx = null; mediaStream = null; sourceNode = null; processorNode = null; ws = null; listening = false;
        document.getElementById('toggle-listening').textContent = 'Start Listening';
        document.getElementById('toggle-listening').classList.remove('listening');
        document.getElementById('mic-status').textContent = 'Idle';
        updateMicLevel(0);
        addLog('system', 'Listening mode stopped', 'warning');
    }
}

document.getElementById('toggle-listening').onclick = async () => {
    if (!listening) await startListening(); else await stopListening();
};

// Audience Service Controls
document.getElementById('get-latest-reaction').onclick = async () => {
    addLog('user', 'Fetching latest audience reaction', 'info');
    try {
        const response = await fetch(`${AUDIENCE_SERVICE_URL}/latest`);
        const data = await parseJsonResponse(response);
        addLog('audience', `Latest reaction: ${data.reaction_type}`, 'success');
        showModal('Latest Audience Reaction', data);
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

document.getElementById('get-reaction-history').onclick = async () => {
    addLog('user', 'Fetching reaction history', 'info');
    try {
        const response = await fetch(`${AUDIENCE_SERVICE_URL}/history`);
        const data = await parseJsonResponse(response);
        addLog('audience', `History retrieved: ${data.count} reactions`, 'success');
        showModal('Reaction History', data);
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

document.getElementById('submit-reaction').onclick = async () => {
    const reaction = document.getElementById('simulate-reaction').value;
    addLog('user', `Simulating ${reaction} reaction`, 'info');

    // Simulate by sending mock audio data
    try {
        const response = await fetch(`${AUDIENCE_SERVICE_URL}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                audio_base64: btoa('mock-audio-data'),  // Mock data
                format: 'pcm16',
                sample_rate: 16000
            })
        });

        const data = await parseJsonResponse(response);
        addLog('audience', `Reaction simulated: ${data.reaction_type}`, 'success');
        showModal('Simulated Reaction', data);
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

// Joke Service Controls
document.getElementById('generate-joke').onclick = async () => {
    const reaction = document.getElementById('joke-reaction').value;
    const theme = document.getElementById('joke-theme').value || null;

    addLog('user', `Generating joke for ${reaction} audience`, 'info');

    try {
        const response = await fetch(`${JOKE_SERVICE_URL}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                audience_reaction: reaction,
                theme: theme,
                include_audio: false  // Don't transfer large audio in frontend
            })
        });

        const data = await parseJsonResponse(response);
        addLog('joke', `Joke: ${data.text}`, 'success');
        showModal('Generated Joke', data);
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

document.getElementById('generate-joke-auto').onclick = async () => {
    const theme = document.getElementById('joke-theme').value || null;

    addLog('user', 'Auto-generating joke (fetching audience reaction)', 'info');

    try {
        const url = new URL(`${JOKE_SERVICE_URL}/generate/auto`);
        if (theme) url.searchParams.append('theme', theme);
        url.searchParams.append('include_audio', 'false');

        const response = await fetch(url, { method: 'POST' });
        const data = await parseJsonResponse(response);
        addLog('joke', `Auto-joke: ${data.text}`, 'success');
        showModal('Auto-Generated Joke', data);
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

document.getElementById('get-stats').onclick = async () => {
    addLog('user', 'Fetching performance statistics', 'info');
    try {
        const response = await fetch(`${JOKE_SERVICE_URL}/stats`);
        const data = await parseJsonResponse(response);
        addLog('joke', `Stats: ${data.total_jokes} jokes, ${(data.engagement_rate * 100).toFixed(1)}% engagement`, 'success');
        showModal('Performance Statistics', data);
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

document.getElementById('reset-generator').onclick = async () => {
    if (!confirm('Are you sure you want to reset the generator?')) return;

    addLog('user', 'Resetting joke generator', 'info');
    try {
        const response = await fetch(`${JOKE_SERVICE_URL}/reset`, { method: 'POST' });
        const data = await parseJsonResponse(response);
        addLog('joke', 'Generator reset successfully', 'success');
        showModal('Reset', data);
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
        showModal('Error', { error: error.message });
    }
};

// Auto Mode
document.getElementById('start-auto-mode').onclick = () => {
    if (autoModeRunning) return;

    autoModeRunning = true;
    document.getElementById('start-auto-mode').disabled = true;
    document.getElementById('stop-auto-mode').disabled = false;

    addLog('system', 'Starting auto performance mode', 'success');

    let jokeCount = 0;
    const reactions = ['laughing', 'neutral', 'silent', 'laughing'];

    autoModeInterval = setInterval(async () => {
        const reaction = reactions[jokeCount % reactions.length];

        try {
            // Simulate audience reaction
            await fetch(`${AUDIENCE_SERVICE_URL}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    audio_base64: btoa(`mock-reaction-${reaction}`),
                    format: 'pcm16',
                    sample_rate: 16000
                })
            });

            // Generate joke
            const response = await fetch(`${JOKE_SERVICE_URL}/generate/auto`, {
                method: 'POST'
            });

            const data = await response.json();
            jokeCount++;

            document.getElementById('auto-mode-status').innerHTML = `
                <strong>Running...</strong><br>
                Jokes delivered: ${jokeCount}<br>
                Last joke: ${data.text.substring(0, 60)}...
            `;
        } catch (error) {
            addLog('auto-mode', `Error: ${error.message}`, 'error');
        }
    }, 10000);  // Every 10 seconds
};

document.getElementById('stop-auto-mode').onclick = () => {
    if (!autoModeRunning) return;

    autoModeRunning = false;
    clearInterval(autoModeInterval);

    document.getElementById('start-auto-mode').disabled = false;
    document.getElementById('stop-auto-mode').disabled = true;

    addLog('system', 'Auto performance mode stopped', 'warning');
    document.getElementById('auto-mode-status').innerHTML = 'Stopped';
};

// Initial log
addLog('system', 'AI Stand-up Comedy Agent Debug Console initialized', 'success');
addLog('system', `Audience Service: ${AUDIENCE_SERVICE_URL}`, 'info');
addLog('system', `Joke Service: ${JOKE_SERVICE_URL}`, 'info');
