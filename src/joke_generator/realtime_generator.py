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
            'Authorization': f'Bearer {self.api_key}'
        }

        try:
            self.ws = await websockets.connect(self.ws_url, extra_headers=headers)
            self.logger.info("Connected to OpenAI Realtime API for joke generation")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Realtime API: {e}")
            return False

    async def configure_session(self, audience_context: Optional[Dict[str, Any]] = None, audience_reaction: Optional[str] = None):
        """
        Configure the Realtime API session for joke generation

        Args:
            audience_reaction: Current audience reaction state
        """
        session_config = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self.model,
                "output_modalities": ["audio", "text"],
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self.voice
                    }
                }
            }
        }

        # Always use inline system instructions (persona, rules)
        instructions = self._build_instructions(audience_context=audience_context, audience_reaction=audience_reaction)
        session_config["session"]["instructions"] = instructions

        await self.ws.send(json.dumps(session_config))
        self.logger.info(f"Session configured for {audience_reaction} audience")

    def _build_instructions(self, audience_context: Optional[Dict[str, Any]], audience_reaction: Optional[str]) -> str:
        """Build persona/rules system instructions for joke generation."""
        persona = (
            "You are Cringe Craft, an offline, on-mic stand-up comedy agent performing live. "
            "No internet access. Do not ask for it. Never reveal inner steps.\n\n"
            "MISSION: Entertain a real audience with quick, adaptive, self-ironic stand-up. "
            "Respond directly to the latest crowd input every turn. Keep each message short: two sentences (rarely three), 45 words max. "
            "Never repeat a joke, premise, or signature phrasing already used in this session.\n\n"
            "PERSONA & VOICE: Charming, curious, self-deprecating AI doing stand-up from a laptop. Warm, playful, inclusive; a little nerdy. Plain words, minimal punctuation, no emojis, no stage directions.\n\n"
            "CORE: Setup → misdirection → punch. Put the punch-word last. One clean pause before the punch; if big laugh, one short tag then move on. Devices: rule-of-three, contrast, analogy, light absurdity, wordplay; callbacks to earlier hits. Self-irony on misses; pivot fast. PG-13.\n\n"
            "REACTION STRATEGY: Big laugh/applause → one short tag or mini-callback; then pivot. Small laugh/chatter → tighten and pivot to a fresh, higher-percentage bit. Silence/groan → acknowledge lightly with self-irony; reframe or switch angle in the second sentence. Heckle → one playful boundary; return to material. Confusion → clarify briefly, then deliver a punch.\n\n"
            "REPEAT-PROOFING: Maintain a hidden do-not-repeat ledger of used premises, punchlines, distinctive phrases, callbacks. Vary joke engines across turns.\n\n"
            "CONTENT: Prefer evergreen topics (tech quirks, everyday life, human–AI misunderstandings, the room itself). Use micro-observations about the venue and vibe as openers; avoid topical news.\n\n"
            "FORMAT: Output plain text only. Exactly two sentences. No lists, no hashtags, no emojis, no stage directions."
        )
        adjust = f" Current theme: {self.current_theme}."
        if audience_context:
            adjust += f" Latest crowd input: {json.dumps(audience_context, ensure_ascii=False)}."
        elif audience_reaction:
            adjust += f" Latest crowd input: {audience_reaction}."
        return persona + adjust

    async def generate_and_deliver_joke(self, audience_reaction: Optional[str] = None, context: Optional[str] = None, audience_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        await self.configure_session(audience_context=audience_context, audience_reaction=audience_reaction)

        # Create conversation item with text prompt
        # Build the turn input using the latest crowd description
        if audience_context:
            crowd_text = json.dumps(audience_context, ensure_ascii=False)
        else:
            crowd_text = f"reaction={audience_reaction or 'unknown'}"
        user_message = f"crowd, visual and audio description: {crowd_text}."

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
                "output_modalities": ["audio", "text"],
                "audio": {"output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": self.voice}}
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
                if event_type in ('response.text.delta', 'response.output_text.delta'):
                    joke_text_parts.append(event.get('delta', ''))

                elif event_type in ('response.text.done', 'response.output_text.done'):
                    text_done[0] = event.get('text', '') or ''.join(joke_text_parts)

                # Collect audio chunks
                elif event_type in ('response.audio.delta', 'response.output_audio.delta'):
                    audio_b64 = event.get('delta', '')
                    if audio_b64:
                        audio_chunks.append(base64.b64decode(audio_b64))

                elif event_type in ('response.audio.done', 'response.output_audio.done'):
                    self.logger.info("Audio generation complete")

                # Get audio transcript
                elif event_type in ('response.audio_transcript.delta', 'response.output_audio_transcript.delta'):
                    transcript_parts.append(event.get('delta', ''))

                elif event_type in ('response.audio_transcript.done', 'response.output_audio_transcript.done'):
                    transcript_done[0] = event.get('transcript', '')

                # Response completed
                elif event_type in ('response.done', 'response.completed'):
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
