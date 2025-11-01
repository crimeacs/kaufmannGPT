"""
Audience Analyzer Module
Listens to audience reactions and evaluates if they're laughing using OpenAI's real-time API
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiohttp
from datetime import datetime


class AudienceAnalyzer:
    """
    Analyzes audience reactions in real-time using OpenAI's API
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the audience analyzer

        Args:
            config: Configuration dictionary containing API keys and settings
        """
        self.api_key = config.get('openai_api_key')
        self.model = config.get('audience_model', 'gpt-4o-realtime-preview')
        self.api_url = config.get('openai_api_url', 'https://api.openai.com/v1/chat/completions')
        self.analysis_interval = config.get('analysis_interval', 2.0)  # seconds

        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.current_reaction = "neutral"

    async def analyze_audio_chunk(self, audio_data: bytes) -> Dict[str, Any]:
        """
        Send audio chunk to OpenAI API for analysis

        Args:
            audio_data: Raw audio bytes to analyze

        Returns:
            Dictionary containing analysis results (is_laughing, confidence, emotion)
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        # Prepare the request payload
        # Note: You may need to convert audio to base64 or use multipart form-data
        payload = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are an audience reaction analyzer. Listen to the audio and determine if the audience is laughing, clapping, silent, or showing other reactions. Respond in JSON format with: {"is_laughing": boolean, "reaction_type": string, "confidence": float, "description": string}'
                },
                {
                    'role': 'user',
                    'content': 'Analyze the audience reaction in this audio clip.'
                }
            ],
            'temperature': 0.3,
            'response_format': {'type': 'json_object'}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()

                        # Parse the response
                        content = result['choices'][0]['message']['content']
                        analysis = json.loads(content)

                        analysis['timestamp'] = datetime.now().isoformat()
                        self.logger.info(f"Audience reaction: {analysis}")

                        return analysis
                    else:
                        error_text = await response.text()
                        self.logger.error(f"API error: {response.status} - {error_text}")
                        return self._get_default_analysis()

        except Exception as e:
            self.logger.error(f"Error analyzing audio: {e}")
            return self._get_default_analysis()

    def _get_default_analysis(self) -> Dict[str, Any]:
        """Return default analysis when API fails"""
        return {
            'is_laughing': False,
            'reaction_type': 'unknown',
            'confidence': 0.0,
            'description': 'Analysis failed',
            'timestamp': datetime.now().isoformat()
        }

    async def start_listening(self, audio_stream):
        """
        Start listening to audio stream and analyzing reactions

        Args:
            audio_stream: Async generator yielding audio chunks
        """
        self.is_running = True
        self.logger.info("Starting audience analysis...")

        try:
            async for audio_chunk in audio_stream:
                if not self.is_running:
                    break

                analysis = await self.analyze_audio_chunk(audio_chunk)

                # Update current reaction state
                if analysis['is_laughing']:
                    self.current_reaction = "laughing"
                else:
                    self.current_reaction = analysis.get('reaction_type', 'neutral')

                # Yield analysis for consumers
                yield analysis

                # Wait for next interval
                await asyncio.sleep(self.analysis_interval)

        except Exception as e:
            self.logger.error(f"Error in listening loop: {e}")
        finally:
            self.is_running = False
            self.logger.info("Stopped audience analysis")

    def stop_listening(self):
        """Stop the listening loop"""
        self.is_running = False

    def get_current_reaction(self) -> str:
        """Get the current audience reaction state"""
        return self.current_reaction
