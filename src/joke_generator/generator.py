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
        self.api_key = config.get('openai_api_key')
        self.model = config.get('joke_model', 'gpt-4o')
        self.tts_model = config.get('tts_model', 'tts-1')
        self.voice = config.get('voice', 'alloy')  # alloy, echo, fable, onyx, nova, shimmer

        self.chat_api_url = 'https://api.openai.com/v1/chat/completions'
        self.tts_api_url = 'https://api.openai.com/v1/audio/speech'

        self.logger = logging.getLogger(__name__)

        # Comedy context
        self.performance_history: List[Dict[str, Any]] = []
        self.current_theme = config.get('initial_theme', 'general observational comedy')
        self.comedy_style = config.get('comedy_style', 'witty and intelligent')

    async def generate_joke(self, audience_reaction: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a joke based on current audience reaction

        Args:
            audience_reaction: Current audience state (laughing, silent, etc.)
            context: Optional context or theme for the joke

        Returns:
            Dictionary containing the joke text and metadata
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        # Build the prompt based on audience reaction
        system_prompt = self._build_system_prompt(audience_reaction)
        user_prompt = self._build_user_prompt(context)

        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.8,
            'max_tokens': 300
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.chat_api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        joke_text = result['choices'][0]['message']['content'].strip()

                        joke_data = {
                            'text': joke_text,
                            'timestamp': datetime.now().isoformat(),
                            'audience_reaction': audience_reaction,
                            'theme': context or self.current_theme
                        }

                        self.logger.info(f"Generated joke: {joke_text[:50]}...")
                        self.performance_history.append(joke_data)

                        return joke_data
                    else:
                        error_text = await response.text()
                        self.logger.error(f"API error: {response.status} - {error_text}")
                        return self._get_fallback_joke(audience_reaction)

        except Exception as e:
            self.logger.error(f"Error generating joke: {e}")
            return self._get_fallback_joke(audience_reaction)

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

    def _get_fallback_joke(self, audience_reaction: str) -> Dict[str, Any]:
        """Return a fallback joke when generation fails"""
        fallback_jokes = [
            "So... my AI joke generator just crashed. That's the most relatable tech moment I've had all day.",
            "You know what's funny? Error 500. Said no one ever.",
            "I'd tell you a UDP joke, but you might not get it."
        ]

        import random
        return {
            'text': random.choice(fallback_jokes),
            'timestamp': datetime.now().isoformat(),
            'audience_reaction': audience_reaction,
            'theme': 'meta-comedy',
            'is_fallback': True
        }

    async def text_to_speech(self, text: str, output_path: Optional[str] = None) -> bytes:
        """
        Convert joke text to speech using OpenAI TTS

        Args:
            text: The joke text to convert
            output_path: Optional path to save the audio file

        Returns:
            Audio data as bytes
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': self.tts_model,
            'input': text,
            'voice': self.voice,
            'response_format': 'mp3'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.tts_api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        self.logger.info(f"Generated TTS audio ({len(audio_data)} bytes)")

                        # Optionally save to file
                        if output_path:
                            with open(output_path, 'wb') as f:
                                f.write(audio_data)
                            self.logger.info(f"Saved audio to {output_path}")

                        return audio_data
                    else:
                        error_text = await response.text()
                        self.logger.error(f"TTS API error: {response.status} - {error_text}")
                        return b''

        except Exception as e:
            self.logger.error(f"Error generating speech: {e}")
            return b''

    async def perform_joke(self, audience_reaction: str, context: Optional[str] = None) -> Dict[str, Any]:
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
        audio_data = await self.text_to_speech(joke_data['text'])

        joke_data['audio'] = audio_data
        joke_data['has_audio'] = len(audio_data) > 0

        return joke_data

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get statistics about the performance so far"""
        if not self.performance_history:
            return {
                'total_jokes': 0,
                'themes': [],
                'audience_engagement': 'unknown'
            }

        laughing_count = sum(1 for j in self.performance_history if j['audience_reaction'] == 'laughing')
        engagement_rate = laughing_count / len(self.performance_history) if self.performance_history else 0

        return {
            'total_jokes': len(self.performance_history),
            'themes': list(set(j['theme'] for j in self.performance_history)),
            'engagement_rate': engagement_rate,
            'audience_engagement': 'high' if engagement_rate > 0.6 else 'medium' if engagement_rate > 0.3 else 'low'
        }

    def update_theme(self, new_theme: str):
        """Update the current comedy theme"""
        self.current_theme = new_theme
        self.logger.info(f"Theme updated to: {new_theme}")
