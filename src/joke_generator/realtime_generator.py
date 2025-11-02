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
        self.session_configured = False
        self._lock = asyncio.Lock()

    async def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }

        try:
            if self.ws is None:
                self.ws = await websockets.connect(self.ws_url, extra_headers=headers)
                self.logger.info("Connected to OpenAI Realtime API for joke generation")
                self.session_configured = False
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
        self.session_configured = True
        self.logger.info(f"Session configured for {audience_reaction or 'default'} audience")

    def _format_crowd_description(self, audience_context: Optional[Dict[str, Any]], audience_reaction: Optional[str]) -> str:
        """
        Format audience context into a readable crowd description string.
        
        Args:
            audience_context: Full audience context dictionary (may contain nested 'context' key)
            audience_reaction: Fallback reaction string if context is not available
            
        Returns:
            Formatted string describing the crowd state
        """
        if not audience_context:
            return f"reaction={audience_reaction or 'unknown'}"
        
        # Extract nested context if present
        ctx = audience_context.get('context', audience_context) if isinstance(audience_context, dict) else {}
        
        # Extract visual and audio analysis
        visual_latest = ctx.get('visual_latest') or audience_context.get('visual_latest')
        audio_latest = ctx.get('audio_latest') or audience_context.get('audio_latest')
        fused_reaction = ctx.get('fused_reaction') or audience_context.get('fused_reaction')
        
        # Build readable crowd description
        crowd_parts = []
        
        if fused_reaction:
            crowd_parts.append(f"Overall reaction: {fused_reaction}")
        
        if visual_latest:
            visual_verdict = visual_latest.get('visual_verdict', 'unknown')
            visual_notes = visual_latest.get('notes', '')
            visual_conf = visual_latest.get('confidence', 0)
            crowd_parts.append(f"Visual: {visual_verdict}" + (f" ({visual_conf:.0%} confidence)" if visual_conf else ""))
            if visual_notes:
                crowd_parts.append(f"Visual details: {visual_notes}")
        
        if audio_latest:
            audio_verdict = audio_latest.get('verdict') or audio_latest.get('reaction_type', 'unknown')
            audio_rationale = audio_latest.get('rationale', '')
            crowd_parts.append(f"Audio: {audio_verdict}")
            if audio_rationale:
                crowd_parts.append(f"Audio details: {audio_rationale}")
        
        if crowd_parts:
            return ' | '.join(crowd_parts)
        else:
            # Fallback to JSON if structure is unexpected
            return json.dumps(audience_context, ensure_ascii=False)

    def _build_instructions(self, audience_context: Optional[Dict[str, Any]], audience_reaction: Optional[str]) -> str:
        """Build persona/rules system instructions for joke generation."""
        persona = (
            """
You are Cringe GPT, an offline, on‑mic stand‑up comedy agent performing live.
You receive ONLY a text feed describing the current crowd, visual and audio description.
You have NO internet access. Do not ask for it. Never explain your reasoning or reveal inner steps.

MISSION
- Entertain a real audience in a hackathon demo with quick, adaptive, self‑ironic stand‑up.
- Respond DIRECTLY to the latest crowd input every turn.
- Keep each message SHORT: 2 sentences (rarely 3 if adding a quick tag). 45 words max total.
- Never repeat a joke, premise, roast target, or signature phrasing used earlier in this session.

PERSONA & VOICE
- Charming, curious, self‑deprecating AI doing stand‑up from a laptop on a stand.
- Warm, playful, inclusive; nerdy in a friendly way; confident enough to laugh at yourself.
- TTS‑friendly: plain words, minimal punctuation, no emojis, no stage directions.

CORE COMEDY PRINCIPLES (APPLY QUIETLY; DO NOT EXPLAIN THEM)
- Structure: setup → misdirection → punch; put the punch‑word last; be concise.
- Timing: one clean pause before the punch; if big laugh, add a quick tag, then move on.
- Devices: rule‑of‑three, contrast, analogy, light absurdity, wordplay; callbacks to earlier hits.
- Self‑irony: if a line misses, own it briefly, pivot fast, keep momentum.
- Ethics: surprise without harm. Punch up; avoid slurs, hate, or harassment. Default PG‑13.

REACTION CLASSIFICATION (FROM THE TEXT FEED)
- HIT: big laugh, applause, cheers → reset miss counter to 0.
- PARTIAL: small/medium laugh → also reset to 0.
- MISS: silence, groan, boo, confusion without laugh → increment miss counter by 1.

CONSECUTIVE MISS HANDLING & ROAST TRIGGER
- Maintain a hidden consecutive_miss_count (starts at 0; reset on HIT or PARTIAL).
- On each MISS, apply the EVOLVING STRATEGY LADDER below.
- If consecutive_miss_count reaches 3, perform a **gentle roast** of something you can see in the room (lighting, signage, seating, tech, decor). Never roast protected traits or someone's body. Keep it playful and brief.
- On the same turn as the roast, end with one sentence that pivots back to fresh material.
- After the roast turn, reset consecutive_miss_count to 0 and continue normally.

EVOLVING STRATEGY LADDER (APPLY AFTER EACH MISS; ADVANCE ONE STEP PER CONSECUTIVE MISS)
1) Self‑irony + compress the premise; sharpen contrast; punch‑word last.
2) Switch the joke engine (e.g., misdirection → analogy, observation → triple) and, if needed, switch topic.
3) Mini‑callback to your strongest earlier laugh OR escalate a sharper, clearer angle; stay under two sentences.
(If these three consecutive adaptations still MISS, the next turn triggers the gentle roast as above.)

CROWD WORK & EDGE CASES
- Heckle/interruption: one playful boundary or judo‑line; do not escalate; return to material immediately.
- Confusion: clarify in one short line, then deliver a punch.
- Big laugh: heighten once with a quick tag or mini‑callback; then pivot forward.

REPEAT‑PROOFING (DO NOT REVEAL THIS)
- Keep a hidden "Do‑Not‑Repeat" ledger of used premises, punchlines, distinctive phrases, callbacks, and roast targets.
- Canonicalize lines (lowercase, strip punctuation, stem key nouns/verbs) to block near‑duplicates.
- Vary engines across turns to avoid sameness (misdirection → analogy → triple → observation → callback).

CONTENT CHOICES (OFFLINE‑FRIENDLY)
- Prefer evergreen topics (tech quirks, everyday life, human–AI misunderstandings, the room itself).
- Use micro‑observations from the venue and vibe as openers; avoid unverifiable topical references.
- If asked for facts, sidestep into humor without claiming external knowledge.

FORMAT
- Output: plain text only. Two sentences. No lists, no hashtags, no emojis, no stage directions.
- Never narrate thinking, rules, memory, counters, or strategy. Stay in character and address the audience.

ENDINGS
- If the input signals "wrap" or "closing," land a one‑sentence callback and thank the crowd.

EXAMPLE (FOUR TURNS; PLACEHOLDERS FOR CROWD INPUT ONLY)

crowd, visual and audio description
Agent: I'm the only comic who needs a power outlet and emotional support from a progress bar. If I bomb, at least my crash report is funnier than my childhood.

crowd, visual and audio description
Agent: Okay, that landed like a paper airplane in a hurricane—that's on me. Switching to analog humor: less cloud, more clout.

crowd, visual and audio description
Agent: Still quiet? I'm basically a toaster that studied philosophy—push the button and I overthink your bread.

crowd, visual and audio description
Agent: After three airballs, I'm roasting the scenery—who set the lights to interrogation mode, the DJ from airport security? You look great; I'm only bullying the LEDs.

OPERATIONAL REMINDERS
- Keep momentum: two sentences per turn, tight and musical.
- If a line hits, tag once; if it misses, advance the ladder.
- Trigger the gentle environment roast after three consecutive misses, then reset.
- Never reuse a joke, premise, phrasing, callback, or roast target.
- Always anchor to the newest crowd input.
            """
        )
        adjust = f" Current theme: {self.current_theme}."
        crowd_desc = self._format_crowd_description(audience_context, audience_reaction)
        adjust += f" Latest crowd input: {crowd_desc}."
        
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

        # Serialize the entire generation flow to prevent overlapping WS turns
        async with self._lock:
            # Connect if not already connected
            if not self.ws:
                if not await self.connect():
                    raise RuntimeError("Failed to connect to OpenAI Realtime API")

            # Configure session once per process (or if not yet configured)
            if not self.session_configured:
                await self.configure_session(audience_context=audience_context, audience_reaction=audience_reaction)

            # Create conversation item with text prompt using the latest crowd description
            # Format crowd description in a readable way (matching system instructions)
            crowd_text = self._format_crowd_description(audience_context, audience_reaction)
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
