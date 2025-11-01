"""
Example usage of the AI Stand-up Comedy Agent

This script demonstrates how to use the agent in different modes.
"""

import asyncio
import sys
import os
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import StandUpAgent
from utils.audio_utils import AudioCapture


def load_config():
    """Load configuration with environment variable support"""
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)

    # Use environment variable if API key not set in config
    if not config.get('openai_api_key'):
        config['openai_api_key'] = os.getenv('OPENAI_API_KEY')

    if not config.get('openai_api_key'):
        print("\n❌ Error: OpenAI API key not found!")
        print("Please set OPENAI_API_KEY environment variable or add it to config.yaml")
        sys.exit(1)

    return config


async def example_basic_performance():
    """
    Example 1: Basic performance without live audience analysis
    This will run a 2-minute routine with simulated audience reactions
    """
    print("=" * 60)
    print("Example 1: Basic Stand-up Performance (Simulated)")
    print("=" * 60)

    agent = StandUpAgent("config.yaml")

    # Perform a 2-minute routine
    await agent.perform_routine(duration_minutes=2)


async def example_with_live_analysis():
    """
    Example 2: Performance with live audience audio analysis
    Note: Requires audio capture implementation
    """
    print("=" * 60)
    print("Example 2: Performance with Live Audience Analysis")
    print("=" * 60)

    agent = StandUpAgent("config.yaml")

    # Create audio capture
    audio_capture = AudioCapture(sample_rate=16000, chunk_duration=2.0)

    # Start performance with live analysis
    try:
        await agent.perform_with_live_audience_analysis(
            audio_capture.capture_stream()
        )
    except KeyboardInterrupt:
        print("\nPerformance stopped")
    finally:
        audio_capture.stop()


async def example_custom_jokes():
    """
    Example 3: Generate individual jokes with custom themes
    """
    print("=" * 60)
    print("Example 3: Custom Joke Generation")
    print("=" * 60)

    from joke_generator import JokeGenerator

    # Load config
    config = load_config()

    generator = JokeGenerator(config)

    themes = [
        "artificial intelligence",
        "programming bugs",
        "cloud computing",
        "video conferences"
    ]

    for theme in themes:
        print(f"\nGenerating joke about: {theme}")
        print("-" * 40)

        joke_data = await generator.perform_joke(
            audience_reaction="neutral",
            context=theme
        )

        print(f"Joke: {joke_data['text']}")
        print(f"Has audio: {joke_data['has_audio']}")
        print()


async def example_adaptive_performance():
    """
    Example 4: Demonstrate adaptive behavior based on reactions
    """
    print("=" * 60)
    print("Example 4: Adaptive Performance")
    print("=" * 60)

    from joke_generator import JokeGenerator

    config = load_config()

    generator = JokeGenerator(config)

    # Simulate different audience reactions
    reactions = ["neutral", "laughing", "silent", "laughing", "laughing"]

    for i, reaction in enumerate(reactions, 1):
        print(f"\n--- Joke #{i} (Audience: {reaction}) ---")

        joke_data = await generator.perform_joke(
            audience_reaction=reaction
        )

        print(f"{joke_data['text']}\n")

        # Show stats after each joke
        stats = generator.get_performance_stats()
        print(f"Engagement: {stats['audience_engagement']} ({stats['engagement_rate']:.1%})")

        await asyncio.sleep(1)

    # Final stats
    print("\n" + "=" * 60)
    print("Performance Statistics")
    print("=" * 60)
    final_stats = generator.get_performance_stats()
    print(f"Total jokes: {final_stats['total_jokes']}")
    print(f"Engagement rate: {final_stats['engagement_rate']:.1%}")
    print(f"Overall engagement: {final_stats['audience_engagement']}")
    print(f"Themes: {', '.join(final_stats['themes'])}")


async def main():
    """Run examples"""
    print("\nAI Stand-up Comedy Agent - Examples\n")

    examples = {
        "1": ("Basic Performance (Simulated)", example_basic_performance),
        "2": ("Live Audience Analysis", example_with_live_analysis),
        "3": ("Custom Joke Generation", example_custom_jokes),
        "4": ("Adaptive Performance Demo", example_adaptive_performance),
    }

    print("Choose an example to run:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")
    print("  q. Quit")

    choice = input("\nEnter your choice (1-4, or q): ").strip()

    if choice.lower() == 'q':
        print("Goodbye!")
        return

    if choice in examples:
        _, example_func = examples[choice]
        await example_func()
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
