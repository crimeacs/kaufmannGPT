"""
Joke Generator Module using OpenAI Realtime API
Generates jokes and delivers them via speech using the Realtime API
"""

import asyncio
import json
import logging
import base64
from typing import Dict, Any, List, Optional
import websockets
from datetime import datetime
import io


class RealtimeJokeGenerator:
    """
    Generates jokes and delivers them via speech using OpenAI's Realtime API
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the joke generator

        Args:
            config: Configuration dictionary containing API keys and settings
        """
        self.api_key = config.get('openai_api_key')
        self.model = config.get('joke_model', 'gpt-realtime')
        self.voice = config.get('voice', 'onyx')
        self.prompt_id = config.get('joke_prompt_id')  # Stored prompt ID

        # WebSocket connection URL
        self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.model}"

        self.logger = logging.getLogger(__name__)

        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []
        self.current_theme = config.get('initial_theme', 'general observational comedy')
        self.comedy_style = config.get('comedy_style', 'witty and intelligent')

        self.ws = None
        self.current_audio_buffer = bytearray()

    async def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'OpenAI-Beta': 'realtime=v1'
        }

        try:
            self.ws = await websockets.connect(self.ws_url, extra_headers=headers)
            self.logger.info("Connected to OpenAI Realtime API for joke generation")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Realtime API: {e}")
            return False

    async def configure_session(self, audience_reaction: str):
        """
        Configure the Realtime API session for joke generation

        Args:
            audience_reaction: Current audience reaction state
        """
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": None,  # Disable turn detection for joke generation
                "temperature": 0.8,
                "max_response_output_tokens": 300
            }
        }

        # Use stored prompt with variables
        if self.prompt_id:
            session_config["session"]["prompt"] = {
                "id": self.prompt_id,
                "variables": {
                    "audience_reaction": {
                        "type": "input_text",
                        "text": audience_reaction
                    },
                    "comedy_style": {
                        "type": "input_text",
                        "text": self.comedy_style
                    },
                    "theme": {
                        "type": "input_text",
                        "text": self.current_theme
                    }
                }
            }
        else:
            # Fallback to inline instructions
            instructions = self._build_instructions(audience_reaction)
            session_config["session"]["instructions"] = instructions

        await self.ws.send(json.dumps(session_config))
        self.logger.info(f"Session configured for {audience_reaction} audience")

    def _build_instructions(self, audience_reaction: str) -> str:
        """Build instructions for joke generation"""
        base = f"You are a stand-up comedian performing live. Your comedy style is {self.comedy_style}."

        if audience_reaction == "laughing":
            adjustment = "The audience is loving it! Keep the momentum going with similar energy."
        elif audience_reaction in ["silent", "neutral"]:
            adjustment = "The audience is quiet. Try a different angle or switch topics to engage them."
        else:
            adjustment = "Adapt your material based on the room's energy."

        return (
            f"{base} {adjustment} "
            f"Generate ONE short joke or bit (2-4 sentences max) about {self.current_theme}. "
            f"Make it punchy and deliver it naturally as if speaking to a live audience."
        )

    async def generate_and_deliver_joke(self, audience_reaction: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a joke and get audio response via Realtime API

        Args:
            audience_reaction: Current audience state
            context: Optional context or theme

        Returns:
            Dictionary with joke text and audio data
        """
        if context:
            self.current_theme = context

        # Connect if not already connected
        if not self.ws:
            if not await self.connect():
                raise RuntimeError("Failed to connect to OpenAI Realtime API")

        # Configure session
        await self.configure_session(audience_reaction)

        # Create conversation item with text prompt
        user_message = f"Tell me a {self.comedy_style} joke about {self.current_theme}"

        await self.ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_message
                    }
                ]
            }
        }))

        # Request response
        await self.ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"]
            }
        }))

        # Collect response
        joke_data = await self._collect_joke_response()
        # Ensure text is present
        if not joke_data.get('text'):
            raise ValueError("No text generated by Realtime API")
        joke_data['audience_reaction'] = audience_reaction
        joke_data['theme'] = self.current_theme

        self.performance_history.append(joke_data)

        return joke_data

    async def _collect_joke_response(self) -> Dict[str, Any]:
        """
        Collect the joke response from WebSocket events

        Returns:
            Dictionary with joke text and audio
        """
        joke_text = ""
        audio_chunks = []
        transcript = ""

        async def collect_messages():
            """Inner function to collect messages"""
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get('type')

                self.logger.debug(f"Event: {event_type}")

                # Collect text response
                if event_type == 'response.text.delta':
                    joke_text_parts.append(event.get('delta', ''))

                elif event_type == 'response.text.done':
                    text_done[0] = event.get('text', '')

                # Collect audio chunks
                elif event_type == 'response.audio.delta':
                    audio_b64 = event.get('delta', '')
                    if audio_b64:
                        audio_chunks.append(base64.b64decode(audio_b64))

                elif event_type == 'response.audio.done':
                    self.logger.info("Audio generation complete")

                # Get audio transcript
                elif event_type == 'response.audio_transcript.delta':
                    transcript_parts.append(event.get('delta', ''))

                elif event_type == 'response.audio_transcript.done':
                    transcript_done[0] = event.get('transcript', '')

                # Response completed
                elif event_type == 'response.done':
                    self.logger.info("Response complete")
                    break

                # Handle errors
                elif event_type == 'error':
                    error_msg = event.get('error', {})
                    self.logger.error(f"API Error: {error_msg}")
                    break

        # Use lists to store parts (for closure)
        joke_text_parts = []
        transcript_parts = []
        text_done = [None]
        transcript_done = [None]

        try:
            # Use wait_for instead of timeout context manager (Python 3.10 compatible)
            await asyncio.wait_for(collect_messages(), timeout=30.0)

            # Combine parts
            joke_text = text_done[0] or ''.join(joke_text_parts)
            transcript = transcript_done[0] or ''.join(transcript_parts)

        except asyncio.TimeoutError:
            self.logger.error("Timeout waiting for response")
            joke_text = ''.join(joke_text_parts) if joke_text_parts else ""
            transcript = ''.join(transcript_parts) if transcript_parts else ""
        except Exception as e:
            self.logger.error(f"Error collecting response: {e}")

        # Combine audio chunks
        audio_data = b''.join(audio_chunks) if audio_chunks else b''

        return {
            'text': joke_text or transcript,
            'audio': audio_data,
            'has_audio': len(audio_data) > 0,
            'timestamp': datetime.now().isoformat()
        }

    

    async def disconnect(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self.logger.info("Disconnected from Realtime API")
            self.ws = None

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get statistics about the performance so far"""
        if not self.performance_history:
            return {
                'total_jokes': 0,
                'themes': [],
                'audience_engagement': 'unknown'
            }

        laughing_count = sum(1 for j in self.performance_history if j.get('audience_reaction') == 'laughing')
        engagement_rate = laughing_count / len(self.performance_history) if self.performance_history else 0

        return {
            'total_jokes': len(self.performance_history),
            'themes': list(set(j.get('theme', 'unknown') for j in self.performance_history)),
            'engagement_rate': engagement_rate,
            'audience_engagement': 'high' if engagement_rate > 0.6 else 'medium' if engagement_rate > 0.3 else 'low'
        }

    def update_theme(self, new_theme: str):
        """Update the current comedy theme"""
        self.current_theme = new_theme
        self.logger.info(f"Theme updated to: {new_theme}")
