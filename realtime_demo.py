"""
Demo for AI Stand-up Agent using OpenAI Realtime API

This demonstrates the WebSocket-based Realtime API for real-time joke generation
with audio output.
"""

import asyncio
import sys
import yaml
import logging
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from joke_generator import RealtimeJokeGenerator
from audience_analyzer import RealtimeAudienceAnalyzer


def load_config():
    """Load configuration with environment variable support"""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Use environment variable if API key not set in config
    if not config.get('openai_api_key'):
        config['openai_api_key'] = os.getenv('OPENAI_API_KEY')

    if not config.get('openai_api_key'):
        print("\n❌ Error: OpenAI API key not found!")
        print("Please set OPENAI_API_KEY environment variable or add it to config.yaml")
        sys.exit(1)

    return config


async def demo_joke_generation():
    """
    Demo: Generate jokes using Realtime API with different audience reactions
    """
    print("=" * 70)
    print("Realtime API Demo: AI Stand-up Comedy Agent")
    print("=" * 70)

    # Load configuration
    config = load_config()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize joke generator
    generator = RealtimeJokeGenerator(config)

    # Simulate different audience reactions
    reactions = [
        ("neutral", "Let's start with something safe"),
        ("laughing", "Great! They're loving it!"),
        ("silent", "Hmm, tough crowd, let's try something else"),
        ("laughing", "Back on track!"),
    ]

    try:
        for i, (reaction, comment) in enumerate(reactions, 1):
            print(f"\n{'─' * 70}")
            print(f"Joke #{i} - Audience: {reaction.upper()}")
            print(f"Context: {comment}")
            print(f"{'─' * 70}")

            # Generate and deliver joke
            joke_data = await generator.generate_and_deliver_joke(
                audience_reaction=reaction
            )

            # Display results
            print(f"\n📝 Joke: {joke_data['text']}")
            print(f"🎵 Has Audio: {'✓' if joke_data['has_audio'] else '✗'}")

            if joke_data['has_audio']:
                # Save audio to file
                audio_path = f"audio_samples/joke_{i}_{reaction}.pcm"
                Path(audio_path).parent.mkdir(parents=True, exist_ok=True)

                with open(audio_path, 'wb') as f:
                    f.write(joke_data['audio'])

                print(f"💾 Audio saved: {audio_path}")
                print(f"   Audio size: {len(joke_data['audio'])} bytes")

            # Wait a bit before next joke
            await asyncio.sleep(2)

        # Show final statistics
        print(f"\n{'=' * 70}")
        print("Performance Statistics")
        print(f"{'=' * 70}")

        stats = generator.get_performance_stats()
        print(f"Total jokes: {stats['total_jokes']}")
        print(f"Engagement rate: {stats['engagement_rate']:.1%}")
        print(f"Overall engagement: {stats['audience_engagement']}")
        print(f"Themes: {', '.join(stats['themes'])}")
        print(f"{'=' * 70}\n")

    finally:
        # Clean up connection
        await generator.disconnect()


async def demo_with_prompt_id():
    """
    Demo: Use stored prompt ID from OpenAI platform
    """
    print("\n" + "=" * 70)
    print("Demo: Using Stored Prompt ID")
    print("=" * 70)

    config = load_config()

    # Check if prompt ID is configured
    prompt_id = config.get('joke_prompt_id')
    if not prompt_id:
        print("\n⚠️  No prompt ID configured!")
        print("To use this demo:")
        print("1. Go to https://platform.openai.com/prompts")
        print("2. Create a stored prompt for comedy generation")
        print("3. Add the prompt ID (pmpt_xxx) to config.yaml")
        print("4. You can use variables in your prompt like {{audience_reaction}}")
        return

    print(f"\n✓ Using prompt ID: {prompt_id}")

    logging.basicConfig(level=logging.INFO)
    generator = RealtimeJokeGenerator(config)

    try:
        print("\nGenerating joke with stored prompt...")
        joke_data = await generator.generate_and_deliver_joke(
            audience_reaction="laughing"
        )

        print(f"\n📝 Joke: {joke_data['text']}")
        print(f"🎵 Has Audio: {'✓' if joke_data['has_audio'] else '✗'}")

        if joke_data['has_audio']:
            audio_path = "audio_samples/stored_prompt_joke.pcm"
            Path(audio_path).parent.mkdir(parents=True, exist_ok=True)

            with open(audio_path, 'wb') as f:
                f.write(joke_data['audio'])

            print(f"💾 Audio saved: {audio_path}")

    finally:
        await generator.disconnect()


async def demo_custom_theme():
    """
    Demo: Generate jokes with custom themes
    """
    print("\n" + "=" * 70)
    print("Demo: Custom Comedy Themes")
    print("=" * 70)

    config = load_config()

    logging.basicConfig(level=logging.INFO)
    generator = RealtimeJokeGenerator(config)

    themes = [
        "artificial intelligence taking over comedy clubs",
        "debugging code at 3am",
        "video conference etiquette",
    ]

    try:
        for theme in themes:
            print(f"\n{'─' * 70}")
            print(f"Theme: {theme}")
            print(f"{'─' * 70}")

            joke_data = await generator.generate_and_deliver_joke(
                audience_reaction="neutral",
                context=theme
            )

            print(f"\n📝 {joke_data['text']}")
            print(f"🎵 Audio: {'✓' if joke_data['has_audio'] else '✗'}")

            await asyncio.sleep(1)

    finally:
        await generator.disconnect()


async def main():
    """Main demo menu"""
    print("\n" + "=" * 70)
    print("AI Stand-up Comedy Agent - Realtime API Demos")
    print("=" * 70)

    demos = {
        "1": ("Basic Joke Generation with Realtime API", demo_joke_generation),
        "2": ("Using Stored Prompt ID", demo_with_prompt_id),
        "3": ("Custom Comedy Themes", demo_custom_theme),
    }

    print("\nAvailable demos:")
    for key, (name, _) in demos.items():
        print(f"  {key}. {name}")
    print("  q. Quit")

    choice = input("\nSelect demo (1-3, or q): ").strip()

    if choice.lower() == 'q':
        print("Goodbye!")
        return

    if choice in demos:
        _, demo_func = demos[choice]
        await demo_func()
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
