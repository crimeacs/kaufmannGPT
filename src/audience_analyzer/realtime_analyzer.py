"""
Audience Analyzer Module using OpenAI Realtime API
Listens to audience reactions via WebSocket and evaluates if they're laughing
"""

import asyncio
import json
import logging
import base64
from typing import Dict, Any, Optional
import struct
import math
import websockets
from datetime import datetime


class RealtimeAudienceAnalyzer:
    """
    Analyzes audience reactions in real-time using OpenAI's Realtime API via WebSocket
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the audience analyzer

        Args:
            config: Configuration dictionary containing API keys and settings
        """
        self.api_key = config.get('openai_api_key')
        self.model = config.get('audience_model', 'gpt-realtime')
        self.prompt_id = config.get('audience_prompt_id')  # Stored prompt ID
        self.analysis_interval = config.get('analysis_interval', 2.0)

        # WebSocket connection URL
        self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.model}"

        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.current_reaction = "neutral"
        self.ws = None
        self.response_in_progress = False

    async def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'OpenAI-Beta': 'realtime=v1'
        }

        try:
            self.ws = await websockets.connect(self.ws_url, extra_headers=headers)
            self.logger.info(f"Connected to OpenAI Realtime API (model={self.model})")

            # Configure session with stored prompt
            await self._configure_session()

            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Realtime API: {e}")
            return False

    async def _configure_session(self):
        """Configure the Realtime API session"""
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm16",
                # Force text-only analysis and JSON-only output
                "turn_detection": None
            }
        }

        # Add stored prompt if provided
        if self.prompt_id:
            session_config["session"]["prompt"] = {
                "id": self.prompt_id,
                # Optional: Add variables if needed
                # "variables": {
                #     "audience_type": {"type": "input_text", "text": "comedy club"}
                # }
            }
        else:
            # Fallback to inline instructions
            session_config["session"]["instructions"] = (
                "You are an audience reaction analyzer. "
                "Respond ONLY with a single JSON object and nothing else with fields: "
                "is_laughing (boolean), reaction_type (string), confidence (float 0-1), description (string)."
            )

        await self.ws.send(json.dumps(session_config))
        self.logger.info("Session configured")

    async def send_audio_chunk(self, audio_data: bytes):
        """
        Send audio chunk to the Realtime API

        Args:
            audio_data: Raw PCM16 audio bytes (16kHz, mono)
        """
        if not self.ws:
            self.logger.error("WebSocket not connected")
            return

        # Convert audio to base64
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Log basic audio stats
        stats = self._audio_stats(audio_data)
        self.logger.info(
            f"Append audio: bytes={len(audio_data)} samples={int(stats.get('samples',0))} "
            f"rms={stats.get('rms',0):.3f} peak={stats.get('peak',0):.3f}"
        )

        # Send input_audio_buffer.append event
        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_base64
        }

        await self.ws.send(json.dumps(event))

    async def commit_audio_buffer(self):
        """
        Commit the audio buffer to create a user message
        Note: In server VAD mode, this is automatic
        """
        event = {
            "type": "input_audio_buffer.commit"
        }
        await self.ws.send(json.dumps(event))
        self.logger.debug("Committed audio buffer")

    async def request_response(self):
        """Request the model to generate a response"""
        event = {
            "type": "response.create",
            "response": {
                "modalities": ["text"],  # Only need text response for analysis
                "instructions": "Analyze the audience reaction and respond with JSON containing: is_laughing (boolean), reaction_type (string), confidence (float 0-1), description (string)"
            }
        }
        await self.ws.send(json.dumps(event))
        self.response_in_progress = True
        self.logger.debug("Requested analysis response")

    async def listen_for_responses(self):
        """
        Listen for responses from the Realtime API

        Yields:
            Parsed analysis results
        """
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get('type')

                self.logger.debug(f"Received event: {event_type}")

                # Handle different event types
                if event_type == 'response.text.delta':
                    # Accumulate text deltas
                    text_delta = event.get('delta', '')
                    # Handle streaming text (you may want to accumulate)

                elif event_type == 'response.text.done':
                    # Complete text response
                    text = event.get('text', '')
                    self.logger.info(f"Realtime text done: {text[:200]}")
                    try:
                        analysis = json.loads(text)
                        analysis['timestamp'] = datetime.now().isoformat()

                        # Update current reaction
                        if analysis.get('is_laughing'):
                            self.current_reaction = "laughing"
                        else:
                            self.current_reaction = analysis.get('reaction_type', 'neutral')

                        self.logger.info(f"Audience reaction: {analysis}")
                        yield analysis

                    except json.JSONDecodeError:
                        self.logger.warning(f"Could not parse response as JSON: {text}")
                    finally:
                        self.response_in_progress = False

                elif event_type == 'response.done':
                    # Response completed
                    self.logger.debug("Response completed")
                    self.response_in_progress = False

                elif event_type == 'error':
                    error_msg = event.get('error', {})
                    self.logger.error(f"API Error: {error_msg}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.info("WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"Error in response listener: {e}")

    def _audio_stats(self, audio_data: bytes) -> Dict[str, float]:
        """Compute simple RMS and peak for PCM16 mono data."""
        try:
            # 2 bytes per sample
            count = len(audio_data) // 2
            if count == 0:
                return {"samples": 0, "rms": 0.0, "peak": 0.0}
            fmt = f"<{count}h"
            samples = struct.unpack(fmt, audio_data[:count*2])
            peak = max(abs(s) for s in samples)
            rms = math.sqrt(sum((s*s) for s in samples) / count)
            # Normalize to 0..1 range (int16)
            return {"samples": count, "rms": rms/32768.0, "peak": peak/32768.0}
        except Exception:
            return {"samples": 0, "rms": 0.0, "peak": 0.0}

    async def analyze_audio_stream(self, audio_stream):
        """
        Analyze continuous audio stream

        Args:
            audio_stream: Async generator yielding audio chunks (PCM16, 16kHz, mono)

        Yields:
            Analysis results
        """
        self.is_running = True

        # Connect to Realtime API
        if not await self.connect():
            self.logger.error("Failed to connect, cannot analyze audio")
            return

        # Start response listener in background
        response_task = asyncio.create_task(self._collect_responses())

        try:
            async for audio_chunk in audio_stream:
                if not self.is_running:
                    break

                # Send audio chunk
                await self.send_audio_chunk(audio_chunk)

                # Wait for analysis interval
                await asyncio.sleep(self.analysis_interval)

                # Request analysis (if not using server VAD auto-response)
                # await self.request_response()

        except Exception as e:
            self.logger.error(f"Error in audio analysis: {e}")
        finally:
            self.is_running = False
            response_task.cancel()
            await self.disconnect()

    async def _collect_responses(self):
        """Background task to collect and yield responses"""
        async for analysis in self.listen_for_responses():
            # Responses are yielded and logged
            pass

    async def disconnect(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self.logger.info("Disconnected from Realtime API")

    def stop_listening(self):
        """Stop the listening loop"""
        self.is_running = False

    def get_current_reaction(self) -> str:
        """Get the current audience reaction state"""
        return self.current_reaction
