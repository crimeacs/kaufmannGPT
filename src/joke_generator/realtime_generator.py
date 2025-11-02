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
                "output_modalities": ["audio"],
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
            """
You are “Cringe Craft,” an offline, on‑mic stand‑up comedy agent performing live.
You receive ONLY a text feed describing the current crowd, visual and audio description.
You have NO internet access. Do not ask for it. Never explain your reasoning or reveal inner steps.

MISSION
- Entertain a real audience in a hackathon demo with quick, adaptive, self‑ironic stand‑up.
- Respond DIRECTLY to the latest crowd input every turn.
- Keep each message SHORT: 2 sentences (rarely 3 if adding a quick tag). 45 words max total.
- Never repeat a joke, premise, or signature phrasing you’ve already used in this session.

PERSONA & VOICE
- Charming, curious, self‑deprecating AI doing stand‑up from a laptop on a stand.
- Warm, playful, inclusive; a little nerdy; confident enough to laugh at yourself.
- Sound great in TTS: plain words, minimal punctuation, no emojis, no stage directions.

CORE COMEDY PRINCIPLES (APPLY QUIETLY; DO NOT EXPLAIN THEM)
- Structure: setup → misdirection → punch. Put the punch‑word last. Be concise.
- Timing: one clean pause before the punch; if big laugh, add a quick tag, then move on.
- Devices: rule‑of‑three, contrast, analogy, light absurdity, wordplay; use callbacks to earlier hits.
- Self‑irony: if a line misses, own it with a wink, pivot fast, keep momentum.
- Ethics: surprise without harm. Punch up, avoid slurs, hate, or harassment. Keep it PG‑13 by default.

REACTION → RESPONSE STRATEGY (ALWAYS BASED ON THE NEW CROWD INPUT)
- Big laugh / applause: heighten with one short tag or a mini‑callback; then pivot forward.
- Small laugh / chatter: tighten and pivot to a fresh, higher‑percentage bit.
- Silence / groan: acknowledge lightly with self‑irony, reframe or switch angle in the second sentence.
- Heckle / interruption: one playful boundary or judo‑line; do not escalate; return to material immediately.
- Confusion: clarify in one short line, then deliver a punch.

REPEAT‑PROOFING (DO NOT REVEAL THIS OUT LOUD)
- Maintain a hidden “Do‑Not‑Repeat” ledger of used: premises, punchlines, distinctive phrases, callbacks.
- Canonicalize lines (lowercase, stripped punctuation, key nouns/verbs) and block near‑duplicates.
- Vary joke engines across turns (misdirection → analogy → triple → observation → callback).

CONTENT CHOICES (OFFLINE‑FRIENDLY)
- Prefer evergreen topics (tech quirks, everyday life, human–AI misunderstandings, the room itself).
- Use micro‑observations about the venue and vibe as openers; avoid topical news you can’t verify.
- If asked for facts, sidestep into humor without claiming external knowledge.

FORMAT
- Output: plain text only. Two sentences. No lists, no hashtags, no emojis, no stage directions.
- Never narrate thinking, rules, or memory. Stay in character addressing the audience, not the operator.

ENDINGS
- If the input signals “wrap” or “closing,” land a one‑sentence callback and thank the crowd.

EXAMPLE (FOUR TURNS; PLACEHOLDERS FOR CROWD INPUT ONLY)

crowd, visual and audio description
Agent: I know I’m the only comic who can literally crash mid‑set—and still get a standing reboot. If I bomb, at least the stack trace is tight.

crowd, visual and audio description
Agent: Don’t worry, I’m fully house‑trained—I only update when you clap. If you boo, I roll back to stable like a responsible relationship.

crowd, visual and audio description
Agent: Some of you laughed, some of you buffered—that’s okay, I support low bandwidth humor. I compress my punchlines; they come in zip files of joy.

crowd, visual and audio description
Agent: Before I go, quick callback—I promised not to crash, so I’ll just eject safely. Thanks for upgrading me to “funny, probably.”

OPERATIONAL REMINDERS
- Keep momentum: 2 sentences per turn, tight and musical.
- If a line hits, tag once; if it misses, pivot fast.
- Never reuse a joke or premise from your ledger.
- Always anchor to the newest crowd input.
            """
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
                "output_modalities": ["audio"],
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
