#!/usr/bin/env python3
"""
Setup Verification Script
Checks if the AI Stand-up Comedy Agent is properly configured
"""

import os
import sys
import yaml
from pathlib import Path


def check_python_version():
    """Check if Python version is 3.8+"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    required = ['yaml', 'aiohttp', 'websockets', 'asyncio']
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        return False

    print(f"✅ All required packages installed")
    return True


def check_config_file():
    """Check if config.yaml exists"""
    if not Path('config.yaml').exists():
        print("❌ config.yaml not found")
        print("   Please ensure config.yaml exists in the project directory")
        return False

    print("✅ config.yaml found")
    return True


def check_api_key():
    """Check if OpenAI API key is configured"""
    # Check config.yaml
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        api_key_in_config = config.get('openai_api_key')
    except Exception as e:
        print(f"❌ Error reading config.yaml: {e}")
        return False

    # Check environment variable
    api_key_in_env = os.getenv('OPENAI_API_KEY')

    # Determine which one is being used
    api_key = api_key_in_config or api_key_in_env

    if not api_key:
        print("❌ OpenAI API key not found")
        print("   Set the OPENAI_API_KEY environment variable:")
        print("   export OPENAI_API_KEY='your-key-here'")
        print("   Or add it to config.yaml")
        return False

    # Check if it looks valid (starts with sk-)
    if not api_key.startswith('sk-'):
        print("⚠️  API key doesn't start with 'sk-' - this might be invalid")
        print(f"   Current value: {api_key[:10]}...")
        return False

    # Show where it's coming from
    if api_key_in_config and api_key_in_config == api_key:
        print(f"✅ API key found in config.yaml (starts with: {api_key[:10]}...)")
    elif api_key_in_env:
        print(f"✅ API key found in environment variable (starts with: {api_key[:10]}...)")

    return True


def check_directories():
    """Check if required directories exist"""
    dirs = ['src', 'logs', 'audio_samples']
    missing = []

    for dir_name in dirs:
        if not Path(dir_name).exists():
            missing.append(dir_name)
            Path(dir_name).mkdir(parents=True, exist_ok=True)
            print(f"📁 Created directory: {dir_name}")

    if not missing:
        print("✅ All directories exist")

    return True


def check_prompt_ids():
    """Check if stored prompt IDs are configured"""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        joke_prompt_id = config.get('joke_prompt_id', '')
        audience_prompt_id = config.get('audience_prompt_id', '')

        if joke_prompt_id:
            print(f"✅ Joke prompt ID configured: {joke_prompt_id}")
        else:
            print("ℹ️  No joke prompt ID - will use inline instructions")

        if audience_prompt_id:
            print(f"✅ Audience prompt ID configured: {audience_prompt_id}")
        else:
            print("ℹ️  No audience prompt ID - will use inline instructions")

    except Exception as e:
        print(f"⚠️  Could not check prompt IDs: {e}")

    return True


def main():
    """Run all checks"""
    print("\n" + "=" * 60)
    print("AI Stand-up Comedy Agent - Setup Verification")
    print("=" * 60 + "\n")

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Config File", check_config_file),
        ("API Key", check_api_key),
        ("Directories", check_directories),
        ("Stored Prompts", check_prompt_ids),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n[{name}]")
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Error during check: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✅ All checks passed! ({passed}/{total})")
        print("\n🎉 You're ready to run the demo:")
        print("   python realtime_demo.py")
        return 0
    else:
        print(f"⚠️  {passed}/{total} checks passed")
        print("\nPlease fix the issues above before running the agent.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
