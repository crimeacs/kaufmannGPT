"""
Main Orchestrator for AI Stand-up Comedy Agent
Coordinates audience analysis and joke generation
"""

import asyncio
import logging
import yaml
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from audience_analyzer import AudienceAnalyzer
from joke_generator import JokeGenerator


class StandUpAgent:
    """
    Main orchestrator for the AI stand-up comedy agent
    Coordinates between audience analysis and joke delivery
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the stand-up agent

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self._setup_logging()

        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AI Stand-up Agent...")

        # Initialize components
        self.audience_analyzer = AudienceAnalyzer(self.config)
        self.joke_generator = JokeGenerator(self.config)

        # Performance state
        self.is_performing = False
        self.performance_start_time = None
        self.joke_count = 0

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file and environment variables"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Use environment variable if API key not set in config
            if not config.get('openai_api_key'):
                config['openai_api_key'] = os.getenv('OPENAI_API_KEY')

            if not config.get('openai_api_key'):
                print("Error: OpenAI API key not found!")
                print("Please set OPENAI_API_KEY environment variable or add it to config.yaml")
                sys.exit(1)

            return config
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            print("Please create a config.yaml file")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    def _setup_logging(self):
        """Set up logging configuration"""
        log_level = self.config.get('log_level', 'INFO')
        log_file = self.config.get('log_file', 'logs/standup_agent.log')

        # Create logs directory if it doesn't exist
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

    async def perform_routine(self, duration_minutes: Optional[int] = None):
        """
        Perform a stand-up comedy routine

        Args:
            duration_minutes: Optional duration for the routine (in minutes)
        """
        self.is_performing = True
        self.performance_start_time = datetime.now()
        self.logger.info("Starting stand-up routine...")

        try:
            # Main performance loop
            while self.is_performing:
                # Check duration limit
                if duration_minutes:
                    elapsed = (datetime.now() - self.performance_start_time).seconds / 60
                    if elapsed >= duration_minutes:
                        self.logger.info(f"Reached time limit ({duration_minutes} minutes)")
                        break

                # Get current audience reaction
                # In a real implementation, this would come from the audio analyzer
                current_reaction = self.audience_analyzer.get_current_reaction()

                self.logger.info(f"Current audience reaction: {current_reaction}")

                # Generate and deliver joke
                joke_data = await self.joke_generator.perform_joke(
                    audience_reaction=current_reaction,
                    context=None
                )

                self.joke_count += 1
                self.logger.info(f"Joke #{self.joke_count}: {joke_data['text']}")

                # Play the audio (in a real implementation)
                if joke_data['has_audio']:
                    await self._play_audio(joke_data['audio'])

                # Wait for joke delivery and audience reaction
                await asyncio.sleep(self.config.get('joke_interval', 5))

                # Simulate checking if we should continue
                # In a real implementation, this could be based on various factors
                if self.joke_count >= self.config.get('max_jokes', 10):
                    self.logger.info("Reached maximum joke count")
                    break

        except KeyboardInterrupt:
            self.logger.info("Performance interrupted by user")
        except Exception as e:
            self.logger.error(f"Error during performance: {e}")
        finally:
            await self.end_performance()

    async def perform_with_live_audience_analysis(self, audio_source):
        """
        Perform with live audience analysis

        Args:
            audio_source: Audio stream source for audience analysis
        """
        self.is_performing = True
        self.performance_start_time = datetime.now()
        self.logger.info("Starting stand-up routine with live audience analysis...")

        try:
            # Start audience analysis in the background
            analysis_task = asyncio.create_task(
                self._run_audience_analysis(audio_source)
            )

            # Main performance loop
            while self.is_performing:
                current_reaction = self.audience_analyzer.get_current_reaction()

                # Generate and deliver joke based on real-time reaction
                joke_data = await self.joke_generator.perform_joke(
                    audience_reaction=current_reaction
                )

                self.joke_count += 1
                self.logger.info(f"Joke #{self.joke_count}: {joke_data['text']}")

                if joke_data['has_audio']:
                    await self._play_audio(joke_data['audio'])

                # Wait before next joke
                await asyncio.sleep(self.config.get('joke_interval', 8))

            # Clean up
            self.audience_analyzer.stop_listening()
            await analysis_task

        except Exception as e:
            self.logger.error(f"Error during live performance: {e}")
        finally:
            await self.end_performance()

    async def _run_audience_analysis(self, audio_source):
        """Background task for continuous audience analysis"""
        try:
            async for analysis in self.audience_analyzer.start_listening(audio_source):
                self.logger.debug(f"Audience analysis: {analysis}")

                # Could trigger adaptive behavior here
                if analysis['is_laughing']:
                    self.logger.info("Audience is laughing! Keep the energy up!")
                elif analysis['confidence'] > 0.7 and not analysis['is_laughing']:
                    self.logger.info("Audience seems quiet, consider changing approach")

        except Exception as e:
            self.logger.error(f"Error in audience analysis: {e}")

    async def _play_audio(self, audio_data: bytes):
        """
        Play audio data
        Note: This is a placeholder. Real implementation would use audio playback library
        """
        # Save audio to file for now
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = f"audio_samples/joke_{timestamp}.mp3"

        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)

        with open(audio_path, 'wb') as f:
            f.write(audio_data)

        self.logger.info(f"Audio saved to {audio_path}")

        # In a real implementation, you would play the audio here
        # using something like pydub, pygame, or a system command
        # For now, we'll just simulate the duration
        await asyncio.sleep(3)  # Simulate audio playback time

    async def end_performance(self):
        """End the performance and show statistics"""
        self.is_performing = False

        if self.performance_start_time:
            duration = (datetime.now() - self.performance_start_time).seconds / 60
            self.logger.info(f"\n{'='*50}")
            self.logger.info("Performance Complete!")
            self.logger.info(f"{'='*50}")
            self.logger.info(f"Duration: {duration:.2f} minutes")
            self.logger.info(f"Total jokes: {self.joke_count}")

            stats = self.joke_generator.get_performance_stats()
            self.logger.info(f"Engagement rate: {stats['engagement_rate']:.2%}")
            self.logger.info(f"Audience engagement: {stats['audience_engagement']}")
            self.logger.info(f"Themes covered: {', '.join(stats['themes'])}")
            self.logger.info(f"{'='*50}\n")

    def stop(self):
        """Stop the performance"""
        self.is_performing = False
        self.audience_analyzer.stop_listening()


async def main():
    """Main entry point"""
    # Load config path from command line or use default
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    # Initialize agent
    agent = StandUpAgent(config_path)

    # Start performance
    # For testing without live audio, use perform_routine()
    await agent.perform_routine(duration_minutes=5)

    # For live performance with audio analysis:
    # audio_source = get_audio_stream()  # Implement audio capture
    # await agent.perform_with_live_audience_analysis(audio_source)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPerformance stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
