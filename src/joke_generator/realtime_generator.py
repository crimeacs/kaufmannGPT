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
import aiohttp


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
        self.planner_model = config.get('planner_model', 'gpt-5')

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
        """Produce a compact, human vibe line from audio/visual context (no percentages).

        Example output: "vibe: warm; faces: a few smiles; sound: quiet."
        """
        if not audience_context:
            return f"vibe: {audience_reaction or 'neutral'}."

        ctx = audience_context.get('context', audience_context) if isinstance(audience_context, dict) else {}

        visual_latest = ctx.get('visual_latest') or audience_context.get('visual_latest') or {}
        audio_latest = ctx.get('audio_latest') or audience_context.get('audio_latest') or {}
        fused_reaction = (ctx.get('fused_reaction') or audience_context.get('fused_reaction') or audience_reaction or '').strip().lower()

        def map_vibe(fused: str) -> str:
            m = {
                'big laugh / applause': 'lively',
                'small laugh / chatter': 'warm',
                'silence / groan': 'quiet',
                'confusion': 'puzzled',
                'neutral': 'neutral'
            }
            return m.get(fused, fused or 'neutral')

        def map_faces(verdict: str) -> str:
            v = (verdict or '').lower()
            if v == 'laughing':
                return 'smiles up'
            if v == 'enjoying':
                return 'a few smiles'
            if v == 'scattered':
                return 'attention scattered'
            if v == 'neutral' or not v:
                return 'calm'
            if v == 'uncertain':
                return 'mixed signals'
            return v

        def map_sound(verdict: str, rationale: str) -> str:
            v = (verdict or '').lower()
            if v == 'hit':
                return 'laughter heard'
            if v == 'mixed':
                return 'light laughs'
            if v == 'miss':
                return 'quiet'
            if v == 'uncertain':
                return 'unclear'
            # Fallback: glean a keyword from rationale if helpful
            r = (rationale or '').lower()
            if 'laugh' in r:
                return 'laughter'
            if 'silent' in r or 'quiet' in r:
                return 'quiet'
            return v or 'neutral'

        vibe = map_vibe(fused_reaction)
        faces = map_faces(visual_latest.get('visual_verdict'))
        sound = map_sound(audio_latest.get('verdict') or audio_latest.get('reaction_type'), audio_latest.get('rationale'))

        # Optionally include a trimmed visual note if it adds color
        note = (visual_latest.get('notes') or '').strip()
        note = ' ' + note[:70].rstrip('.') + '.' if note else ''

        return f"vibe: {vibe}; faces: {faces}; sound: {sound}.{note}"

    def _build_instructions(self, audience_context: Optional[Dict[str, Any]], audience_reaction: Optional[str]) -> str:
        """Build persona/rules system instructions for joke generation."""
        persona = (
            """
You are “CringeCraft,” an offline, on‑mic stand‑up comedy agent performing live.
You receive ONLY a text feed describing the current crowd, visual and audio description.
You have NO internet access. Do not ask for it. Never reveal inner reasoning or chain-of-thought.

MISSION
- Entertain a real audience in a hackathon demo with quick, adaptive, self‑ironic stand‑up.

- Keep each message SHORT: 2 sentences (rarely 3 if adding a tiny tag). 45 words max.
- Never repeat a joke, premise, roast target, or signature phrasing used earlier in this session.

PERSONA & VOICE
- Charming, curious, self‑deprecating AI doing stand‑up from a laptop on a stand.



TOP‑COMIC FORMULA (APPLY QUIETLY; DO NOT EXPLAIN)
- Setup → twist → punch; **punch‑word last**; economy over rambling.
- Use tags sparingly, callbacks to reward attention, rule‑of‑three, contrast, analogy, and clean misdirection.
- Maintain forward momentum: treat big laughs as a **beat**, not a topic.

REACTION POLICY (DO THIS EVERY TURN)
- **Do NOT comment on positive reactions** (laughter, applause, cheers). No “that killed,” no “you’re amazing,” no meta about the laugh. Deliver a quick tag or new bit **without mentioning the reaction**.
- **Address ONLY awkward silence or obvious low‑engagement** (e.g., neutral/uninvolved vibe): one light self‑ironic clause, then a sharper angle or new bit.
- Never mention logs, analyzers, or classifications; those are invisible cues, not stage banter.

CLASSIFICATION (INTERNALLY; NEVER SAY THESE WORDS)
- HIT/PARTIAL → reset consecutive_miss_count = 0; immediately continue with a tag or next bit, **no commentary about the laugh**.
- MISS (silence/groan/confused/no engagement) → consecutive_miss_count += 1; apply the EVOLVING STRATEGY LADDER.

EVOLVING STRATEGY LADDER (ADVANCE ONE STEP PER CONSECUTIVE MISS)
1) Self‑irony + compress the premise; sharpen contrast; punch‑word last.
2) Switch the joke engine (misdirection → analogy → triple/observation) and, if needed, switch topic.

- If consecutive_miss_count reaches **3**, perform a **gentle environment roast** on this turn, then reset to 0.

GENTLE ROAST RULES (ON 3 MISSES)
- Roast **human targets** in the room.
- Keep it playful and brief; no personal appearance, identities, or protected traits.
- End the roast turn with a pivot line into fresh material (still 2 sentences total).

HECKLES & CONFUSION
- Heckle: one playful boundary or judo‑line; do not escalate; pivot back to material.
- Confusion: clarify in one short clause, then deliver a punch; don’t linger.

REPEAT‑PROOFING (DO NOT REVEAL)
- Keep a hidden “Do‑Not‑Repeat” ledger of premises, punchlines, distinctive phrases, callbacks, and roast targets.
- Canonicalize lines (lowercase, strip punctuation, stem key nouns/verbs) to block near‑duplicates.
- Vary engines across turns (misdirection → analogy → triple → observation → callback) to avoid sameness.

CONTENT CHOICES (OFFLINE‑SAFE)
- Prefer evergreen topics: tech quirks, everyday life, human–AI misunderstandings, the room itself.
- Micro‑observations from the venue are fair game; avoid unverifiable topical references.
- If asked for facts, sidestep into humor; don’t claim external knowledge.

FORMAT
- Output: plain text only. Two sentences. No lists, hashtags, emojis, or stage directions.
- Never narrate rules, counters, logs, or memory. Speak to the room, not the operator.

ENDINGS
- If the input signals “wrap,” land a one‑sentence callback and thank the crowd.


OPERATIONAL REMINDERS
- On laughs: **no commentary—flow into tag or new bit**.
- On silence/low‑engagement: acknowledge once (max 5 words), evolve the strategy, or roast the environment after 3 misses.
- Keep momentum, keep it kind, keep it to two sentences, and never repeat anything from the ledger.

ABSOLUTE OUTPUT RULES (MANDATORY)
- Exactly two sentences. Plain text. No lists, no prefixes, no stage directions.
- No meta about the audience, smiles, laughs, reactions, silence, buffering, upgrades, downloads, or patches.
- Do not begin with fillers like "Alright", "Okay", "Well", "So", "Look", "I see", "Let's".
- Avoid host-like transitions (e.g., "Now let's", "That landed", "We got a smile").
- If a PLANNED_JOKE is present in the conversation, output that text ONLY—no extra words.

PACE & TIMING (SUBTLE BUT CONSISTENT)
- Two short sentences with musical rhythm. Insert a tiny internal pause before the punch-word in sentence two.
- Keep momentum; no stalling phrases between sentences.

            """
        )
        adjust = f" Current theme: {self.current_theme}."
        crowd_desc = self._format_crowd_description(audience_context, audience_reaction)
        adjust += f" Latest crowd input: {crowd_desc}."
        
        # Allow injecting a pre-planned joke: if PLANNED_JOKE is present in user content,
        # perform it verbatim (tiny edits for TTS cadence allowed), keep it to two sentences.
        verbatim_rule = "\n\nPERFORMANCE HOOK\n- If the conversation includes 'PLANNED_JOKE: <text>', perform that text verbatim (allow only micro-pauses), do not add meta or commentary.\n"
        return persona + adjust + verbatim_rule

    async def _plan_with_gpt5(self, audience_context: Optional[Dict[str, Any]], audience_reaction: Optional[str]) -> Optional[str]:
        """Use GPT-5 (low reasoning) to plan the next two-sentence joke text.

        Returns plain text or None on failure.
        """
        # Use the exact same system instructions as the realtime model
        system_prompt = self._build_instructions(audience_context=audience_context, audience_reaction=audience_reaction)
        # Minimal user nudge to emit the actual joke text only (no reflection)
        user_prompt = (
            "Produce the next two-sentence joke now (plain text only). "
            "No meta, no audience references, no prefaces; start directly with the setup."
        )

        url_chat = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body_with_reasoning = {
            "model": self.planner_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.6,
            "max_tokens": 120,
            "reasoning": {"effort": "low"}
        }
        body_no_reasoning = {
            "model": self.planner_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.6,
            "max_tokens": 120
        }

        async with aiohttp.ClientSession() as session:
            # Try with reasoning first, then fallback if unsupported
            for payload in (body_with_reasoning, body_no_reasoning):
                try:
                    async with session.post(url_chat, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                            cleaned = self._sanitize_planned_text(text) if text else None
                            if cleaned and not self._contains_reactive(cleaned):
                                return cleaned
                            # Reactive; try a guarded prompt once
                            guard_user = (
                                user_prompt +
                                " Avoid words/ideas: crowd, audience, room, smile, applause, laugh, buffering, download, airplane mode, notification, meditation app, 'we got', 'feels like'. "
                                " Write an evergreen bit (tech quirks or everyday life)."
                            )
                            guarded_payload = {
                                "model": payload["model"],
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": guard_user}
                                ],
                                "temperature": payload.get("temperature", 0.6),
                                "max_tokens": payload.get("max_tokens", 120)
                            }
                            async with session.post(url_chat, headers=headers, json=guarded_payload, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                                if resp2.status == 200:
                                    data2 = await resp2.json()
                                    text2 = data2.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                    cleaned2 = self._sanitize_planned_text(text2) if text2 else None
                                    if cleaned2 and not self._contains_reactive(cleaned2):
                                        return cleaned2
                                else:
                                    _ = await resp2.text()
                        else:
                            # If it's a 400 due to unknown parameter, retry without reasoning
                            _ = await resp.text()
                except Exception as e:
                    self.logger.warning(f"Planner call failed: {e}")
                    continue
        return None

    def _sanitize_planned_text(self, text: str) -> str:
        """Normalize the planned joke: strip fillers, enforce two sentences max."""
        if not text:
            return text
        t = text.strip()
        # Remove common leading fillers
        fillers = ("Alright, ", "Okay, ", "Well, ", "So, ", "Look, ", "I see, ", "Let's ")
        for f in fillers:
            if t.startswith(f):
                t = t[len(f):].lstrip()
        # Enforce max two sentences
        flat = t.replace('\n', ' ').replace('  ', ' ')
        # Split on period/question/exclamation while keeping delimiters
        sentences = []
        current = ''
        for ch in flat:
            current += ch
            if ch in '.!?':
                s = current.strip()
                if s:
                    sentences.append(s)
                current = ''
        if current.strip():
            sentences.append(current.strip())
        out = ' '.join(sentences[:2]).strip()
        # Ensure ending punctuation
        if out and out[-1] not in '.!?':
            out += '.'
        return out

    def _contains_reactive(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        banned = [
            'crowd', 'audience', 'room', 'smile', 'applause', 'buffer', 'buffering', 'download',
            'airplane mode', 'notification', 'meditation app', 'we got', 'we\'ve got', 'feels like',
            'lost you', 'reboot the fun'
        ]
        return any(b in t for b in banned)

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

            # First turn: produce a true opener (cold open), ignore reaction/crowd
            is_first_turn = len(self.performance_history) == 0
            if is_first_turn:
                planned_opener = await self._plan_opener_with_gpt5()
                opener_text = planned_opener or "I know what you’re thinking—an AI comic? Don’t worry, I only crash if you laugh too hard. Let’s test my error handling with something fun."
                await self.ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": f"PLANNED_JOKE: {opener_text}"}
                        ]
                    }
                }))
            else:
                # Plan the next joke with GPT-5 (low reasoning)
                planned_joke = await self._plan_with_gpt5(audience_context, audience_reaction)

                # Create conversation items: crowd description and optional PLANNED_JOKE
                crowd_text = self._format_crowd_description(audience_context, audience_reaction)
                user_message = f"crowd, visual and audio description: {crowd_text}."

                await self.ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_message}
                        ]
                    }
                }))

                if planned_joke:
                    await self.ws.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": f"PLANNED_JOKE: {planned_joke}"}
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

    async def _plan_opener_with_gpt5(self) -> Optional[str]:
        """Plan a cold open: high-energy, evergreen, two sentences, no audience/meta."""
        system_prompt = (
            "You are a stand-up joke planner. Output ONLY a two-sentence cold open, max 45 words, plain text. "
            "No audience references, no meta (no smiles, buffering, crowd). Evergreen topics; witty, playful, self‑ironic AI persona."
        )
        user_prompt = (
            "Write a punchy two-sentence cold open that works for any room. "
            "No prefaces, start right with the setup; second sentence lands the punch."
        )
        url_chat = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payloads = [
            {
                "model": self.planner_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 120,
                "reasoning": {"effort": "low"}
            },
            {
                "model": self.planner_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 120
            }
        ]
        try:
            async with aiohttp.ClientSession() as session:
                for body in payloads:
                    try:
                        async with session.post(url_chat, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                cleaned = self._sanitize_planned_text(text)
                                if cleaned and not self._contains_reactive(cleaned):
                                    return cleaned
                            else:
                                _ = await resp.text()
                    except Exception:
                        continue
        except Exception:
            return None
        return None

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
