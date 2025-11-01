// Configuration
const AUDIENCE_SERVICE_URL = 'http://localhost:8002';
const JOKE_SERVICE_URL = 'http://localhost:8003';

// State
let autoScrollEnabled = true;
let autoModeRunning = false;
let autoModeInterval = null;

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

// Audience Service Controls
document.getElementById('get-latest-reaction').onclick = async () => {
    addLog('user', 'Fetching latest audience reaction', 'info');
    try {
        const response = await fetch(`${AUDIENCE_SERVICE_URL}/latest`);
        const data = await response.json();
        showModal('Latest Audience Reaction', data);
        addLog('audience', `Latest reaction: ${data.reaction_type}`, 'success');
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
    }
};

document.getElementById('get-reaction-history').onclick = async () => {
    addLog('user', 'Fetching reaction history', 'info');
    try {
        const response = await fetch(`${AUDIENCE_SERVICE_URL}/history`);
        const data = await response.json();
        showModal('Reaction History', data);
        addLog('audience', `History retrieved: ${data.count} reactions`, 'success');
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
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

        const data = await response.json();
        addLog('audience', `Reaction simulated: ${data.reaction_type}`, 'success');
    } catch (error) {
        addLog('audience', `Error: ${error.message}`, 'error');
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

        const data = await response.json();
        showModal('Generated Joke', data);
        addLog('joke', `Joke: ${data.text}`, 'success');
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
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
        const data = await response.json();

        showModal('Auto-Generated Joke', data);
        addLog('joke', `Auto-joke: ${data.text}`, 'success');
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
    }
};

document.getElementById('get-stats').onclick = async () => {
    addLog('user', 'Fetching performance statistics', 'info');
    try {
        const response = await fetch(`${JOKE_SERVICE_URL}/stats`);
        const data = await response.json();
        showModal('Performance Statistics', data);
        addLog('joke', `Stats: ${data.total_jokes} jokes, ${(data.engagement_rate * 100).toFixed(1)}% engagement`, 'success');
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
    }
};

document.getElementById('reset-generator').onclick = async () => {
    if (!confirm('Are you sure you want to reset the generator?')) return;

    addLog('user', 'Resetting joke generator', 'info');
    try {
        const response = await fetch(`${JOKE_SERVICE_URL}/reset`, { method: 'POST' });
        const data = await response.json();
        addLog('joke', 'Generator reset successfully', 'success');
    } catch (error) {
        addLog('joke', `Error: ${error.message}`, 'error');
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
