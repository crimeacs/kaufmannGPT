"""
Audience Analysis Service
FastAPI service for analyzing audience reactions
Listens on port 8000
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from collections import deque
import logging
import json
import base64
import sys
import asyncio
from pathlib import Path
from datetime import datetime
import time
import yaml
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from audience_analyzer import RealtimeAudienceAnalyzer, AudienceAnalyzer
from .error_utils import map_exception, error_payload

# Initialize FastAPI app
app = FastAPI(
    title="Audience Analysis Service",
    description="Analyzes audience reactions in real-time",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# State management: Store recent reactions
reaction_history: deque = deque(maxlen=100)
latest_reaction: Optional[Dict[str, Any]] = None

# Log streaming
log_queue: asyncio.Queue = asyncio.Queue()

# Load configuration
def load_config():
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    if not config.get('openai_api_key'):
        config['openai_api_key'] = os.getenv('OPENAI_API_KEY')

    return config

config = load_config()


# Request/Response Models
class AudioAnalysisRequest(BaseModel):
    audio_base64: str
    format: str = "pcm16"
    sample_rate: int = 16000


class AudioAnalysisResponse(BaseModel):
    is_laughing: bool
    reaction_type: str
    confidence: float
    description: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


# Initialize analyzers (singletons)
realtime_analyzer = None
rest_analyzer = None


def get_realtime_analyzer():
    global realtime_analyzer
    if realtime_analyzer is None:
        realtime_analyzer = RealtimeAudienceAnalyzer(config)
    return realtime_analyzer


def get_rest_analyzer():
    global rest_analyzer
    if rest_analyzer is None:
        rest_analyzer = AudienceAnalyzer(config)
    return rest_analyzer


@app.on_event("startup")
async def startup_event():
    logger.info("Audience Analysis Service starting...")
    logger.info(f"OpenAI API Key configured: {'Yes' if config.get('openai_api_key') else 'No'}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Audience Analysis Service shutting down...")
    if realtime_analyzer:
        await realtime_analyzer.disconnect()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="audience-analyzer",
        version="1.0.0"
    )


@app.post("/analyze", response_model=AudioAnalysisResponse)
async def analyze_audio(request: AudioAnalysisRequest):
    """
    Analyze audio for audience reactions

    Accepts base64-encoded audio and returns reaction analysis
    """
    global latest_reaction

    try:
        # Decode audio
        audio_data = base64.b64decode(request.audio_base64)

        log_msg = f"Analyzing audio chunk ({len(audio_data)} bytes)"
        logger.info(log_msg)
        await log_queue.put({"service": "audience", "message": log_msg, "level": "info"})

        # Get analyzer instance
        analyzer_instance = get_rest_analyzer()

        # Analyze audio
        analysis = await analyzer_instance.analyze_audio_chunk(audio_data)

        # Store in history
        reaction_history.append(analysis)
        latest_reaction = analysis

        log_msg = f"Analysis complete: {analysis['reaction_type']} (confidence: {analysis['confidence']:.2f})"
        logger.info(log_msg)
        await log_queue.put({"service": "audience", "message": log_msg, "level": "info"})

        return AudioAnalysisResponse(**analysis)

    except Exception as e:
        error_msg = f"Error analyzing audio: {e}"
        logger.error(error_msg)
        await log_queue.put({"service": "audience", "message": error_msg, "level": "error"})
        status, payload = map_exception(e)
        return JSONResponse(status_code=status, content=payload)


@app.post("/analyze-file")
async def analyze_audio_file(file: UploadFile = File(...)):
    """
    Analyze audio file for audience reactions

    Accepts audio file upload and returns reaction analysis
    """
    try:
        # Read file content
        audio_data = await file.read()

        logger.info(f"Analyzing audio file: {file.filename} ({len(audio_data)} bytes)")

        # Get analyzer instance
        analyzer_instance = get_rest_analyzer()

        # Analyze audio
        analysis = await analyzer_instance.analyze_audio_chunk(audio_data)

        return JSONResponse(content=analysis)

    except Exception as e:
        logger.error(f"Error analyzing audio file: {e}")
        status, payload = map_exception(e)
        return JSONResponse(status_code=status, content=payload)


@app.websocket("/ws/analyze")
async def websocket_analyze(websocket: WebSocket):
    """
    WebSocket endpoint for continuous audio analysis using Realtime API

    Client sends audio chunks (base64 PCM16), server streams back analysis
    """
    await websocket.accept()
    logger.info("WebSocket connection established for audio analysis")

    rt = get_realtime_analyzer()
    # Ensure realtime connection is ready
    if not getattr(rt, 'ws', None):
        ok = await rt.connect()
        if not ok:
            await websocket.send_json(error_payload("UPSTREAM_ERROR", "Failed to connect to Realtime API"))
            await websocket.close()
            return

    last_request_ts = 0.0

    async def forward_responses():
        try:
            async for analysis in rt.listen_for_responses():
                # Update state and logs
                reaction_history.append(analysis)
                global latest_reaction
                latest_reaction = analysis
                msg = f"WS analysis: {analysis.get('reaction_type','unknown')} (conf {analysis.get('confidence',0):.2f})"
                logger.info(msg)
                await log_queue.put({"service": "audience", "message": msg, "level": "info"})
                # Forward to client
                await websocket.send_json(analysis)
        except Exception as e:
            logger.error(f"Error forwarding realtime responses: {e}")

    forward_task = asyncio.create_task(forward_responses())

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                audio_base64 = message.get('audio')

                if audio_base64:
                    audio_data = base64.b64decode(audio_base64)
                    # Debug: log audio stats
                    try:
                        stats = rt._audio_stats(audio_data)
                        msg = f"WS recv chunk: bytes={len(audio_data)}, samples={int(stats.get('samples',0))}, rms={stats.get('rms',0):.3f}, peak={stats.get('peak',0):.3f}"
                        logger.info(msg)
                        await log_queue.put({"service": "audience", "message": msg, "level": "info"})
                    except Exception:
                        pass

                    await rt.send_audio_chunk(audio_data)

                    now = time.time()
                    if now - last_request_ts > 1.5:
                        # Commit and request analysis periodically
                        try:
                            await rt.commit_audio_buffer()
                        except Exception:
                            pass
                        await rt.request_response()
                        dbg = "Committed buffer and requested analysis"
                        logger.info(dbg)
                        await log_queue.put({"service": "audience", "message": dbg, "level": "info"})
                        last_request_ts = now
                else:
                    await websocket.send_json(error_payload("VALIDATION_ERROR", "No audio data provided"))
            except json.JSONDecodeError:
                await websocket.send_json(error_payload("VALIDATION_ERROR", "Invalid JSON format"))
            except Exception as e:
                logger.error(f"Error in WebSocket analysis: {e}")
                status, payload = map_exception(e)
                await websocket.send_json(payload)

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        try:
            forward_task.cancel()
        except Exception:
            pass


@app.get("/latest")
async def get_latest_reaction():
    """
    Get the most recent audience reaction

    Used by joke service to coordinate comedy delivery
    """
    if latest_reaction is None:
        return JSONResponse(status_code=404, content=error_payload("NO_DATA", "No reactions analyzed yet"))

    return JSONResponse(content=latest_reaction)


@app.get("/history")
async def get_reaction_history():
    """Get recent reaction history"""
    return {
        "count": len(reaction_history),
        "reactions": list(reaction_history)
    }


@app.get("/stream/logs")
async def stream_logs():
    """
    Server-Sent Events endpoint for real-time log streaming

    Clients can subscribe to receive log messages as they occur
    """
    async def event_generator():
        while True:
            try:
                # Wait for new log message
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)

                # Format as SSE
                data = json.dumps(log_entry)
                yield f"data: {data}\n\n"

            except asyncio.TimeoutError:
                # Send keep-alive and continue loop
                yield f": keepalive\n\n"
            except Exception as e:
                logger.error(f"Error in log stream: {e}")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Audience Analysis Service",
        "version": "1.0.0",
        "endpoints": {
            "POST /analyze": "Analyze audio (base64)",
            "POST /analyze-file": "Analyze audio file",
            "GET /latest": "Get most recent reaction (for joke service)",
            "GET /history": "Get recent reaction history",
            "GET /stream/logs": "SSE stream of real-time logs",
            "WebSocket /ws/analyze": "Continuous analysis stream",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
else:
    # ASGI wrapper to normalize multiple slashes in path (affects HTTP and WebSocket)
    # This makes ws paths like //ws/analyze work, preventing client-side URL bugs from breaking the WS.
    import re
    _inner_app = app

    async def _normalized_app(scope, receive, send):
        if scope.get('type') in ('http', 'websocket'):
            path = scope.get('path') or ''
            if '//' in path:
                # Create a shallow copy of scope to avoid mutating original
                scope = dict(scope)
                scope['path'] = re.sub(r'/+', '/', path)
        await _inner_app(scope, receive, send)

    app = _normalized_app
