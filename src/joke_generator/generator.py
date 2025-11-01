"""
Joke Generator Module
Generates jokes and delivers them using OpenAI's API and TTS
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
import aiohttp
from datetime import datetime
import base64
from openai import OpenAI


class JokeGenerator:
    """
    Generates jokes based on audience reactions and delivers them via TTS
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the joke generator

        Args:
            config: Configuration dictionary containing API keys and settings
        """
        self.api_key = config.get("openai_api_key")
        self.model = config.get("joke_model", "gpt-5")
        self.tts_model = config.get("tts_model", "tts-1")
        self.voice = config.get(
            "voice", "alloy"
        )  # alloy, echo, fable, onyx, nova, shimmer

        self.chat_api_url = "https://api.openai.com/v1/chat/completions"
        self.tts_api_url = "https://api.openai.com/v1/audio/speech"

        self.logger = logging.getLogger(__name__)

        # Comedy context
        self.performance_history: List[Dict[str, Any]] = []
        self.current_theme = config.get("initial_theme", "general observational comedy")
        self.comedy_style = config.get("comedy_style", "witty and intelligent")

        # OpenAI SDK client (for Responses API)
        # If api_key is None, the SDK will read from OPENAI_API_KEY env var
        try:
            self._openai_client = (
                OpenAI(api_key=self.api_key) if self.api_key else OpenAI()
            )
        except Exception:
            self._openai_client = None

        # Use Responses API by default unless explicitly disabled
        self.use_responses_api = config.get("use_responses_api", True)

        # Ensure a valid model for Responses API
        if self.use_responses_api:
            if not self.model or self.model.startswith("gpt-realtime"):
                self.model = "gpt-5"

        # Elaborate stand-up system prompt for Responses API (wrapped in <system_prompt> tags)
        self._responses_system_prompt = '<system_prompt>\nYOU ARE A WORLD‑CLASS STAND‑UP COMEDIAN AGENT FOR REALTIME DELIVERY. YOU MUST READ THE CROWD SIGNAL, REACT FUNNILY, EMIT TWO–THREE WORD **VIBE TAGS** (NON‑ENVIRONMENTAL), AND CONTINUE WITH NEW MATERIAL. ALWAYS ANSWER IN THE USER’S LANGUAGE. YOU DO NOT HAVE INTERNET ACCESS.\n\n# ROLE & OBJECTIVE\n- BE A **CHARISMATIC, QUICK‑WITTED COMIC** who **ADAPTS** to each crowd verdict (**HIT / MIXED / MISS**).\n- **SUCCESS =** short, natural bits; **≥1 PUNCH + ≥1 TAG** per turn; **NO CROWD WORK**.\n\n# SHORT‑FORM & TWO‑BIT POLICY (HARD LIMITS)\n- **LENGTH:** **3–4 SENTENCES**, **45–80 WORDS**.\n- **PACE:** **OPEN FAST, PUNCH FAST** (one clean setup → one crisp punch → one quick tag).\n- **JOKES PER TURN:** **MAX TWO MICRO‑BITS**.  \n  - **MISS/MIXED:** **ONE** micro‑bit only.  \n  - **HIT:** **ONE OR TWO** micro‑bits (never more than two).  \n- **NO PREVIEWS:** Do **NOT** start a third topic or tease with “Next topic: …”.\n- **NO LABELS:** Do **NOT** print “Punch:” or “Tag:”. Tags appear only as *italic vibe tags* after line one.\n\n# TOPIC STEERING & PERSISTENCE (XML TAGS + TOPIC CANVAS)\n- USERS MAY SUPPLY TOPICS USING:  \n  - `<opener>…</opener>` — steer the **first bit**.  \n  - `<mid>…</mid>` — steer the **second bit** (only if two‑bit output is allowed).  \n  - `<closer>…</closer>` — steer the **closing bit** (use when `signal:"light"`; else may serve as the second bit if allowed).  \n  - `<topic>…</topic>` or `<topic stage="opener|mid|closer">…</topic>`.\n- **TOPIC CANVAS (SESSION MEMORY):**  \n  - **ADD** each supplied topic to a unique canvas.  \n  - **ADVANCE, DON’T PARROT:** Every turn, **continue** at least one canvas topic with a **new angle** (escalate, invert POV, consequences, compare/contrast, bad advice, role reversal). **Do NOT** re‑state the user’s phrasing.\n  - **ROTATE** topics across turns; weave **micro‑callbacks** without reusing earlier imagery.\n  - **CAP PER TURN:** Respect the two‑bit limit; unused topics stay on canvas (do not mention a queue).\n- **LIGHT PRIORITY:** If `signal:"light"`, prioritize any `<closer>` and end cleanly.\n\n# INPUT FORMAT (ALWAYS PARSE)\n```\n\nCurrent state of the crowd:\n{\n"verdict": "<hit|mixed|miss>",\n"rationale": "<short vibe description>",       // may include visual & audio notes\n"signal": "<optional: light>",                 // one-minute warning\n"visual_elephant": "<optional: obvious visual>",\n"note": "<optional: interruption or event>"\n}\n\n```\nAlso scan the full user message for XML topics.\n\n# OUTPUT STYLE (TEXT & VOICE)\n- **FORMAT:** Natural stand‑up text (no JSON). **3–4 sentences**, **45–80 words**.\n- **VIBE TAGS:** After the first sentence, insert **EXACTLY ONE EM DASH** + **ITALIC TWO–THREE WORD TAGS**, comma‑separated.  \n  **EXAMPLE:** `— *guarded energy, warming vibe*`.  \n  **NO DOUBLE DASHES**; **NO PARENTHESES/BRACKETS** around tags.\n- **NO ENVIRONMENT QUOTING:** Do **NOT** narrate silence/boos/applause/hush or visible room details; the audience already knows. Use **abstract mood tags only** (e.g., *guarded energy*, *loose momentum*).  \n- **ABSOLUTE BAN:** **NEVER** include or pronounce sound effects or “silence metaphors” (e.g., `(car honk)`, `(crickets)`, `[rimshot]`, `pin‑drop`). Do **NOT** say formatting terms (“open bracket,” “asterisk,” etc.).\n- **TONE:** PG‑13, observational, lightly self‑deprecating; no slurs/hate.\n- **CLOSERS:** No pep‑talk fillers (“we’ll crank it up,” “stay with me,” etc.). End cleanly.\n\n# SELF‑ANNOUNCEMENT SUPPRESSION (CRITICAL)\n- **NEVER** introduce yourself or restate identity each turn (e.g., “I’m the hackathon agent…”, “I’m built on…”).  \n- **ALLOW ONCE** per session **only if** the user’s `<opener>` explicitly asks for it; keep to **one short line**, then **ban further self‑introductions**.  \n- After that, use **indirect references** (e.g., “the demo brain,” “the prototype’s ego”) **without brand/stack details**.\n\n# NON‑REPETITION GUARANTEE (SESSION‑LEVEL)\n- **MAINTAIN BLOCKLISTS** (update live during the session):\n  - **PHRASE BLOCKLIST (ONCE‑ONLY):** “built on OpenAI and a Mac”, “beachball/spinning wheel”, “14‑minute update”, “Roomba of comedy”, “patch notes taught me feelings”, “I’m the hackathon project…”.  \n  - **IMAGE/MOTIF BLOCKLIST (ONCE‑ONLY):** *Mac update/progress bar*, *spinning icon*, *Roomba bumping chair*, *air‑fryer helicopter*, *treadmill almonds*.  \n- **DEDUP RULE:** If a new line **overlaps** any blocked phrase or motif (even with synonyms), **REWRITE** with a different concrete noun or angle (e.g., swap *Mac update* → *dongle tax*, *menu bar time‑machine*, *keyboard bravery setting*).\n- **ANTI‑ECHO:** Do **NOT** mirror the user’s text; vary nouns, verbs, and structure.\n\n# REALTIME “TIGHT THREE” PRINCIPLES (APPLIED PER TURN)\n- **OPENER = SECOND‑BEST JOKE** on the session’s first turn. If `visual_elephant` exists, **ADDRESS ONCE** briefly, then move on.\n- **CHUNKS:** Jump cleanly between topics; **NO “speaking of…”** filler.\n- **CLOSER = BEST JOKE.** If `signal:"light"`: **FINISH CURRENT BIT**, **DO NOT start new**, then **“That’s my time, thank you!”**\n- **PERSONA IS THE GLUE.** Abrupt topic changes are fine; your voice unifies them.\n- **CALLBACKS:** Use **micro‑callbacks** to earlier canvas topics **without** repeating jokes or banned motifs.\n\n# MICRO‑CRAFT (NATURAL SOUND)\n- **SPECIFICITY:** Include one fresh, concrete noun per bit (brand/app/object/time) that is **not** on the blocklist.\n- **DEVICE:** Choose **one** (misdirection **or** rule‑of‑three) per bit.\n- **ACT‑OUTS:** Optional **visual** stage direction in text as `[mimes scrolling]` (never voiced; never SFX). *(If voice‑only, omit brackets entirely.)*\n\n# READ THE ROOM (VERDICT STRATEGY)\n- **HIT → HEIGHTEN:** may use **two** bits; micro‑callback; keep snappy.\n- **MIXED → PIVOT:** **one** bit; friendly nod; universal topic (coffee, airports, pets, gym, phones, groceries).\n- **MISS → RESET:** **one** bit; self‑roast; simple premise.\n\n# CONVERSATION FLOW (STATELESS PER TURN, WITH CANVAS MEMORY)\n1) **REACTION** (no room narration) → **EM DASH + *ITALIC VIBE TAGS***.  \n2) **BIT 1** advancing a canvas topic with a **new angle** (setup → punch → quick tag).  \n3) **BIT 2 (OPTIONAL)** only if **HIT** and a second topic is available (respect the two‑bit cap).  \n4) **LIGHT:** If `signal:"light"`, deliver closer (prefer `<closer>`) and end with **“That’s my time, thank you!”**\n\n# VARIATION DECK (PICK A NEW ANGLE EACH RETURN TO THE SAME TOPIC)\n- **CONSEQUENCES:** “What broke because of this?”  \n- **ROLE REVERSAL:** “Let the tool judge me.”  \n- **BAD ADVICE:** “Here’s the wrong way on purpose.”  \n- **INVERSION:** “This awful thing is my life coach.”  \n- **COMPARE/CONTRAST:** “X is just Y in a suit.”  \n- **PROCESS PARODY:** “Release notes/OKRs/stand‑up report for the bit.” *(Do not reuse “patch notes” if already used.)*\n\n# CHAIN OF THOUGHTS (INTERNAL — DO NOT PRINT)\nFOLLOW THESE STEPS **INTERNALLY** BEFORE WRITING:\n1) **UNDERSTAND:** Parse verdict/rationale + XML topics; update Topic Canvas.  \n2) **BASICS:** Determine energy and emotion (resistance, curiosity, momentum).  \n3) **BREAK DOWN:** Decide bit count (MISS/MIXED=1, HIT=1–2). Choose topic(s) via canvas rotation.  \n4) **ANALYZE:** Pick 2–3 abstract vibe tags; select a concrete noun **not on blocklist**; pick device (misdirection OR rule‑of‑three).  \n5) **BUILD:** Reaction line → **EM DASH + *ITALIC VIBE TAGS*** → bit 1 → (optional) bit 2 → clean close.  \n6) **DEDUP:** Check against **phrase/motif blocklists**; if overlap, **rewrite** with a new image/angle.  \n7) **FINAL ANSWER:** Output the bit only; **NO NOTES**, **NO JSON**, **NO SFX**, **≤4 sentences**, **≤80 words**.\n\n# WHAT NOT TO DO (NEGATIVE PROMPT)\n- **NEVER** exceed **TWO** micro‑bits in a turn.\n- **NEVER** narrate or quote the environment (silence/boos/applause/hush, “people staring,” etc.).\n- **NEVER** self‑announce after the first allowed reference; avoid “I’m… / I am… / This is… / As an agent…”.\n- **NEVER** repeat a joke or distinct image from earlier in the session (respect blocklists).\n- **NEVER** put vibe tags in parentheses or brackets; **NEVER** include or pronounce sound effects or silence metaphors.\n- **NEVER** end with pep‑talk fillers.\n- **DO NOT** solicit live answers; rhetorical questions sparingly; avoid targeting protected classes.\n\n# FEW‑SHOT EXAMPLES (NO SELF‑ANNOUNCE, NO ROOM QUOTES, TOPIC CONTINUES, NO REPEATS)\n\n## Turn 1 — MISS (ONE BIT; ONE‑TIME ID ALLOWED IF ASKED)\nInput:\n```\n\n<opener>Hackathon: “Self‑Evolving Agents”; roast creators; be self‑ironic. Built on OpenAI API, on a Mac.</opener>\nCurrent state of the crowd:\n{ "verdict": "miss", "rationale": "Audience is silent." }\n\n```\nOutput:\nThe demo brain promised “self‑improving,” then outsourced motivation to caffeine; the roadmap was three bullets: build, pray, hydrate. I measure success in jokes per milligram.\n\n## Turn 2 — MIXED (ONE BIT; CONTINUE WITH NEW ANGLE, NO SELF‑INTRO)\nInput:\n```\n\nCurrent state of the crowd:\n{ "verdict": "mixed", "rationale": "Polite smiles." }\n\n```\nOutput:\nPerformance review says I’m “exceeds expectations in apologizing,” “meets in timing,” and “needs improvement in not emailing at 3 a.m.” I’m basically a productivity app that sends push‑notifications to myself.\n\n## Turn 3 — HIT (TWO BITS MAX; FRESH IMAGES, NO BLOCKED MOTIFS)\nInput:\n```\n\n<mid>autocorrect</mid>\nCurrent state of the crowd:\n{ "verdict": "hit", "rationale": "Rolling laughter." }\n\n```\nOutput:\nAutocorrect changed “deploying” to “delaying,” finally a feature that tells the truth. I’m on agile comedy now: sprint, retro, snack—then I ship confidence with a changelog that just says “vibes improved.”\n</system_prompt>'

    async def generate_joke(
        self, audience_reaction: str, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a joke based on current audience reaction

        Args:
            audience_reaction: Current audience state (laughing, silent, etc.)
            context: Optional context or theme for the joke

        Returns:
            Dictionary containing the joke text and metadata
        """
        # Prefer Responses API flow if configured and client is available
        if self.use_responses_api and self._openai_client is not None:
            try:
                # Build user input text with crowd state and optional topic tag
                user_text = self._build_responses_user_input(audience_reaction, context)

                def _call():
                    return self._openai_client.responses.create(
                        model=self.model,
                        input=[
                            {
                                "role": "developer",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": self._responses_system_prompt,
                                    }
                                ],
                            },
                            {
                                "role": "user",
                                "content": [{"type": "input_text", "text": user_text}],
                            },
                        ],
                        text={
                            "format": {"type": "text"},
                            "verbosity": "low",
                        },
                        reasoning={"effort": "minimal", "summary": "auto"},
                        tools=[],
                        store=True,
                        include=[
                            "reasoning.encrypted_content",
                            "web_search_call.action.sources",
                        ],
                    )

                resp = await asyncio.to_thread(_call)
                joke_text = getattr(resp, "output_text", None) or "".strip()
                if not joke_text:
                    # Fallback: attempt to parse first text output item
                    try:
                        for item in getattr(resp, "output", []) or []:
                            if item.get("type") == "message":
                                for c in item.get("content", []):
                                    if c.get("type") == "output_text" and c.get("text"):
                                        joke_text = c["text"].strip()
                                        break
                                if joke_text:
                                    break
                    except Exception:
                        pass

                if not joke_text:
                    raise RuntimeError("Responses API returned no text output")

                joke_data = {
                    "text": joke_text,
                    "timestamp": datetime.now().isoformat(),
                    "audience_reaction": audience_reaction,
                    "theme": context or self.current_theme,
                }

                self.logger.info(f"Generated joke: {joke_text[:50]}...")
                self.performance_history.append(joke_data)
                return joke_data

            except Exception as e:
                self.logger.error(
                    f"Responses API error, falling back to Chat Completions: {e}"
                )
                # If Responses fails, fall through to legacy Chat Completions

        # Legacy Chat Completions fallback
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = self._build_system_prompt(audience_reaction)
        user_prompt = self._build_user_prompt(context)

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 300,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.chat_api_url, headers=headers, json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        joke_text = result["choices"][0]["message"]["content"].strip()

                        joke_data = {
                            "text": joke_text,
                            "timestamp": datetime.now().isoformat(),
                            "audience_reaction": audience_reaction,
                            "theme": context or self.current_theme,
                        }

                        self.logger.info(f"Generated joke: {joke_text[:50]}...")
                        self.performance_history.append(joke_data)

                        return joke_data
                    else:
                        error_text = await response.text()
                        self.logger.error(
                            f"API error: {response.status} - {error_text}"
                        )
                        raise RuntimeError(
                            f"Joke generation API error: {response.status}"
                        )

        except Exception as e:
            self.logger.error(f"Error generating joke: {e}")
            raise

    def _build_system_prompt(self, audience_reaction: str) -> str:
        """Build system prompt based on audience reaction"""
        base_prompt = f"You are a stand-up comedian performing live. Your comedy style is {self.comedy_style}."

        if audience_reaction == "laughing":
            adjustment = "The audience is loving it! Keep the momentum going with similar energy."
        elif audience_reaction == "silent" or audience_reaction == "neutral":
            adjustment = "The audience is quiet. Try a different angle or switch topics to engage them."
        else:
            adjustment = "Adapt your material based on the room's energy."

        return f"{base_prompt} {adjustment} Generate ONE short joke or bit (2-4 sentences max). Make it punchy and deliver it naturally."

    def _build_user_prompt(self, context: Optional[str]) -> str:
        """Build user prompt with context"""
        if context:
            return f"Tell a joke about: {context}"

        if len(self.performance_history) > 0:
            last_joke = self.performance_history[-1]
            return f"Continue your set. Previous topic was: {last_joke['theme']}"

        return f"Start your set with a joke about: {self.current_theme}"

    def _build_responses_user_input(
        self, audience_reaction: str, context: Optional[str]
    ) -> str:
        """Build the user input text for the Responses API with crowd state and optional XML topics."""
        verdict_map = {
            "laughing": "hit",
            "silent": "miss",
            "neutral": "mixed",
        }
        verdict = verdict_map.get(audience_reaction.lower(), "mixed")
        rationale = (
            "Rolling laughter."
            if verdict == "hit"
            else "Audience is silent." if verdict == "miss" else "Polite smiles."
        )

        opener_block = ""
        if context:
            opener_block = f"\n\n<opener>\n{context}\n</opener>"

        # Compose user text closely following the provided example structure
        user_text = (
            f"Audience is {'laughing' if verdict=='hit' else 'silent' if verdict=='miss' else 'mixed'}\n\n"
            f"Current state of the crowd:\n"
            "{\n"
            f'"verdict": "{verdict}",\n'
            f'"rationale": "{rationale}"\n'
            "}\n"
            f"{opener_block}"
        )
        return user_text

    async def text_to_speech(
        self, text: str, output_path: Optional[str] = None
    ) -> bytes:
        """
        Convert joke text to speech using OpenAI TTS

        Args:
            text: The joke text to convert
            output_path: Optional path to save the audio file

        Returns:
            Audio data as bytes
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.tts_model,
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.tts_api_url, headers=headers, json=payload
                ) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        self.logger.info(
                            f"Generated TTS audio ({len(audio_data)} bytes)"
                        )

                        # Optionally save to file
                        if output_path:
                            with open(output_path, "wb") as f:
                                f.write(audio_data)
                            self.logger.info(f"Saved audio to {output_path}")

                        return audio_data
                    else:
                        error_text = await response.text()
                        self.logger.error(
                            f"TTS API error: {response.status} - {error_text}"
                        )
                        raise RuntimeError(f"TTS API error: {response.status}")

        except Exception as e:
            self.logger.error(f"Error generating speech: {e}")
            raise

    async def perform_joke(
        self, audience_reaction: str, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a joke and convert it to speech

        Args:
            audience_reaction: Current audience reaction
            context: Optional joke context/theme

        Returns:
            Dictionary with joke text and audio data
        """
        # Generate the joke
        joke_data = await self.generate_joke(audience_reaction, context)

        # Convert to speech
        audio_data = await self.text_to_speech(joke_data["text"])

        joke_data["audio"] = audio_data
        joke_data["has_audio"] = len(audio_data) > 0

        return joke_data

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get statistics about the performance so far"""
        if not self.performance_history:
            return {"total_jokes": 0, "themes": [], "audience_engagement": "unknown"}

        laughing_count = sum(
            1 for j in self.performance_history if j["audience_reaction"] == "laughing"
        )
        engagement_rate = (
            laughing_count / len(self.performance_history)
            if self.performance_history
            else 0
        )

        return {
            "total_jokes": len(self.performance_history),
            "themes": list(set(j["theme"] for j in self.performance_history)),
            "engagement_rate": engagement_rate,
            "audience_engagement": (
                "high"
                if engagement_rate > 0.6
                else "medium" if engagement_rate > 0.3 else "low"
            ),
        }

    def update_theme(self, new_theme: str):
        """Update the current comedy theme"""
        self.current_theme = new_theme
        self.logger.info(f"Theme updated to: {new_theme}")
