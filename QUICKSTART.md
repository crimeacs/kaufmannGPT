# Quick Start Guide

Get your AI Stand-up Comedy Agent running in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- OpenAI API key (get one at https://platform.openai.com/api-keys)

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Set Your API Key

The easiest way is to set an environment variable:

### On macOS/Linux:
```bash
export OPENAI_API_KEY="sk-your-actual-key-here"
```

### On Windows (Command Prompt):
```cmd
set OPENAI_API_KEY=sk-your-actual-key-here
```

### On Windows (PowerShell):
```powershell
$env:OPENAI_API_KEY="sk-your-actual-key-here"
```

## Step 3: Run a Demo

```bash
python realtime_demo.py
```

Select option **1** to see the Realtime API in action!

## What Happens Next?

The demo will:
1. Connect to OpenAI's Realtime API via WebSocket
2. Generate jokes based on simulated audience reactions
3. Create audio files with speech output
4. Show performance statistics

## Viewing the Output

Audio files are saved to `audio_samples/` in PCM16 format.

To play PCM16 audio files, you can convert them to MP3:
```bash
# Using ffmpeg (if installed)
ffmpeg -f s16le -ar 24000 -ac 1 -i audio_samples/joke_1_neutral.pcm output.mp3
```

## Next Steps

### Use Your Own Stored Prompts

1. Go to https://platform.openai.com/prompts
2. Create a new prompt with variables like `{{audience_reaction}}`
3. Copy the prompt ID (starts with `pmpt_`)
4. Edit `config.yaml`:
   ```yaml
   joke_prompt_id: "pmpt_your_prompt_id_here"
   ```

### Customize the Comedy Style

Edit `config.yaml`:
```yaml
comedy_style: "sarcastic and edgy"
initial_theme: "modern technology"
voice: "nova"  # Change the voice
```

### Run More Examples

Try different demos:
```bash
python realtime_demo.py
# Choose option 2 for stored prompts
# Choose option 3 for custom themes
```

## Troubleshooting

### "API key not found" Error

Make sure you've set the `OPENAI_API_KEY` environment variable:
```bash
echo $OPENAI_API_KEY  # Should show your key
```

### Connection Errors

Check your internet connection and firewall settings. The Realtime API uses WebSocket connections to:
```
wss://api.openai.com/v1/realtime
```

### Import Errors

Make sure you installed all dependencies:
```bash
pip install -r requirements.txt
```

## Configuration Options

Key settings in `config.yaml`:

| Setting | Options | Description |
|---------|---------|-------------|
| `joke_model` | `gpt-realtime`, `gpt-4o` | Model for joke generation |
| `voice` | `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` | Voice for TTS |
| `comedy_style` | Any text | Style of comedy |
| `joke_interval` | Number (seconds) | Wait time between jokes |
| `temperature` | 0.0 - 1.0 | Creativity level |

## Getting Help

- Check the [main README](README.md) for detailed documentation
- See [REALTIME_API_GUIDE.md](REALTIME_API_GUIDE.md) for API reference
- Review example code in `realtime_demo.py`

## Project Structure

```
AGI_hackathon/
├── realtime_demo.py          ← Start here!
├── config.yaml               ← Configuration
├── src/
│   ├── joke_generator/
│   │   └── realtime_generator.py
│   └── audience_analyzer/
│       └── realtime_analyzer.py
└── audio_samples/            ← Generated audio
```

Happy coding! 🎭🤖
