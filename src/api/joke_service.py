"""
Joke Generation Service
FastAPI service for generating and delivering jokes
Listens on port 8001
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json
import base64
import sys
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
import yaml
import os
import io

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from joke_generator import RealtimeJokeGenerator
from .error_utils import map_exception

# Initialize FastAPI app
app = FastAPI(
    title="Joke Generation Service",
    description="Generates and delivers jokes with audio",
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

# Audience service URL (for coordinated services)
AUDIENCE_SERVICE_URL = os.getenv('AUDIENCE_SERVICE_URL', 'http://localhost:8000')


# Request/Response Models
class JokeRequest(BaseModel):
    audience_reaction: str = "neutral"
    theme: Optional[str] = None
    include_audio: bool = True


class JokeResponse(BaseModel):
    text: str
    theme: str
    audience_reaction: str
    has_audio: bool
    audio_base64: Optional[str] = None
    timestamp: str


class PerformanceStatsResponse(BaseModel):
    total_jokes: int
    themes: list
    engagement_rate: float
    audience_engagement: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


# Initialize generator (singleton)
generator = None


def get_generator():
    global generator
    if generator is None:
        generator = RealtimeJokeGenerator(config)
    return generator


async def fetch_latest_audience_reaction() -> Dict[str, Any]:
    """
    Fetch the latest audience reaction from the audience service

    Returns a default reaction if the service is unavailable
    """
    try:
        log_msg = f"Fetching latest audience reaction from {AUDIENCE_SERVICE_URL}/latest"
        logger.info(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{AUDIENCE_SERVICE_URL}/latest", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    log_msg = f"Received audience reaction: {data.get('reaction_type', data.get('verdict', 'unknown'))}"
                    logger.info(log_msg)
                    await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})
                    return data
                else:
                    log_msg = f"Audience service returned status {response.status}"
                    logger.warning(log_msg)
                    await log_queue.put({"service": "joke", "message": log_msg, "level": "warning"})
                    # Fallback when no reactions yet
                    return {"verdict": "uncertain", "rationale": "no reactions yet", "reaction_type": "neutral"}

    except asyncio.TimeoutError:
        log_msg = "Timeout fetching audience reaction"
        logger.warning(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "warning"})
        return {"verdict": "uncertain", "rationale": "timeout", "reaction_type": "neutral"}
    except Exception as e:
        log_msg = f"Error fetching audience reaction: {e}"
        logger.error(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "error"})
        return {"verdict": "uncertain", "rationale": "error", "reaction_type": "neutral"}


@app.on_event("startup")
async def startup_event():
    logger.info("Joke Generation Service starting...")
    logger.info(f"OpenAI API Key configured: {'Yes' if config.get('openai_api_key') else 'No'}")
    logger.info(f"Voice: {config.get('voice', 'onyx')}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Joke Generation Service shutting down...")
    if generator:
        await generator.disconnect()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="joke-generator",
        version="1.0.0"
    )


@app.post("/generate", response_model=JokeResponse)
async def generate_joke(request: JokeRequest):
    """
    Generate a joke based on audience reaction

    Returns joke text and optionally audio (base64-encoded)
    """
    try:
        log_msg = f"Generating joke for {request.audience_reaction} audience"
        logger.info(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})

        # Get generator instance
        generator_instance = get_generator()

        # Generate joke
        joke_data = await generator_instance.generate_and_deliver_joke(
            audience_reaction=request.audience_reaction,
            context=request.theme
        )

        log_msg = f"Joke generated: {joke_data['text'][:50]}..."
        logger.info(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})

        # Prepare response
        response = JokeResponse(
            text=joke_data['text'],
            theme=joke_data.get('theme', 'general'),
            audience_reaction=joke_data['audience_reaction'],
            has_audio=joke_data['has_audio'],
            timestamp=joke_data['timestamp']
        )

        # Include audio if requested
        if request.include_audio and joke_data['has_audio']:
            audio_base64 = base64.b64encode(joke_data['audio']).decode('utf-8')
            response.audio_base64 = audio_base64

        return response

    except Exception as e:
        logger.error(f"Error generating joke: {e}")
        status, payload = map_exception(e)
        return JSONResponse(status_code=status, content=payload)


@app.post("/generate/audio")
async def generate_joke_audio(request: JokeRequest):
    """
    Generate a joke and return audio file directly

    Returns PCM16 audio as a downloadable file
    """
    try:
        logger.info(f"Generating joke audio for {request.audience_reaction} audience")

        # Get generator instance
        generator_instance = get_generator()

        # Generate joke
        joke_data = await generator_instance.generate_and_deliver_joke(
            audience_reaction=request.audience_reaction,
            context=request.theme
        )

        if not joke_data['has_audio']:
            raise HTTPException(status_code=500, detail="Failed to generate audio")

        # Return audio as response
        return Response(
            content=joke_data['audio'],
            media_type="audio/pcm",
            headers={
                "Content-Disposition": "attachment; filename=joke.pcm",
                "X-Joke-Text": joke_data['text'],
                "X-Theme": joke_data.get('theme', 'general')
            }
        )

    except Exception as e:
        logger.error(f"Error generating joke audio: {e}")
        status, payload = map_exception(e)
        return JSONResponse(status_code=status, content=payload)


@app.post("/generate/auto", response_model=JokeResponse)
async def generate_joke_auto(theme: Optional[str] = None, include_audio: bool = True):
    """
    Auto-generate a joke by fetching latest audience reaction

    This endpoint coordinates with the audience service to get the current
    reaction and then generates an appropriate joke.
    """
    try:
        # Fetch latest audience reaction
        audience_data = await fetch_latest_audience_reaction()
        # Map new analyzer schema to a short reaction label
        verdict = audience_data.get('verdict')
        if verdict == 'hit':
            audience_reaction = 'big laugh / applause'
        elif verdict == 'mixed':
            audience_reaction = 'small laugh / chatter'
        elif verdict == 'miss':
            audience_reaction = 'silence / groan'
        elif verdict == 'uncertain':
            audience_reaction = 'confusion'
        else:
            audience_reaction = audience_data.get('reaction_type', 'neutral')

        log_msg = f"Auto-generating joke for {audience_reaction} audience"
        logger.info(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})

        # Get generator instance
        generator_instance = get_generator()

        # Generate joke
        joke_data = await generator_instance.generate_and_deliver_joke(
            audience_reaction=audience_reaction,
            context=theme,
            audience_context=audience_data
        )

        log_msg = f"Auto-joke generated: {joke_data['text'][:50]}..."
        logger.info(log_msg)
        await log_queue.put({"service": "joke", "message": log_msg, "level": "info"})

        # Prepare response
        response = JokeResponse(
            text=joke_data['text'],
            theme=joke_data.get('theme', 'general'),
            audience_reaction=joke_data['audience_reaction'],
            has_audio=joke_data['has_audio'],
            timestamp=joke_data['timestamp']
        )

        # Include audio if requested
        if include_audio and joke_data['has_audio']:
            audio_base64 = base64.b64encode(joke_data['audio']).decode('utf-8')
            response.audio_base64 = audio_base64

        return response

    except Exception as e:
        error_msg = f"Error in auto-generate: {e}"
        logger.error(error_msg)
        await log_queue.put({"service": "joke", "message": error_msg, "level": "error"})
        status, payload = map_exception(e)
        return JSONResponse(status_code=status, content=payload)


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


@app.get("/stats", response_model=PerformanceStatsResponse)
async def get_stats():
    """
    Get performance statistics

    Returns statistics about jokes generated and audience engagement
    """
    try:
        generator_instance = get_generator()
        stats = generator_instance.get_performance_stats()

        return PerformanceStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset")
async def reset_generator():
    """Reset the generator and clear history"""
    global generator
    if generator:
        await generator.disconnect()
        generator = None

    return {"status": "reset", "message": "Generator reset successfully"}


@app.websocket("/ws/perform")
async def websocket_perform(websocket: WebSocket):
    """
    WebSocket endpoint for continuous joke performance

    Client sends audience reactions, server responds with jokes
    """
    await websocket.accept()
    logger.info("WebSocket connection established for joke performance")

    generator_instance = get_generator()

    try:
        while True:
            # Receive audience reaction
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                audience_reaction = message.get('audience_reaction', 'neutral')
                theme = message.get('theme')

                logger.info(f"Generating joke for WebSocket client (reaction: {audience_reaction})")

                # Generate joke
                joke_data = await generator_instance.generate_and_deliver_joke(
                    audience_reaction=audience_reaction,
                    context=theme
                )

                # Prepare response
                response = {
                    'text': joke_data['text'],
                    'theme': joke_data.get('theme', 'general'),
                    'has_audio': joke_data['has_audio'],
                    'timestamp': joke_data['timestamp']
                }

                # Include audio if available
                if joke_data['has_audio']:
                    response['audio_base64'] = base64.b64encode(joke_data['audio']).decode('utf-8')

                # Send joke back
                await websocket.send_json(response)

            except json.JSONDecodeError:
                await websocket.send_json({
                    "error": "Invalid JSON format"
                })
            except Exception as e:
                logger.error(f"Error in WebSocket joke generation: {e}")
                await websocket.send_json({
                    "error": str(e)
                })

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Joke Generation Service",
        "version": "1.0.0",
        "voice": config.get('voice', 'onyx'),
        "comedy_style": config.get('comedy_style', 'witty'),
        "audience_service_url": AUDIENCE_SERVICE_URL,
        "endpoints": {
            "POST /generate": "Generate joke with specified audience reaction",
            "POST /generate/auto": "Auto-generate joke (fetches audience reaction automatically)",
            "POST /generate/audio": "Generate joke and return audio file",
            "GET /stream/logs": "SSE stream of real-time logs",
            "GET /stats": "Get performance statistics",
            "POST /reset": "Reset generator and history",
            "WebSocket /ws/perform": "Continuous joke performance stream",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
