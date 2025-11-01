# AI Stand-up Comedy Agent

An AI-powered stand-up comedy agent that generates and delivers jokes while analyzing audience reactions in real-time using OpenAI's Realtime API.

## 🚀 Quick Start with Docker

The fastest way to get started:

```bash
# Set your API key
export OPENAI_API_KEY="your-key-here"

# Start all services
./start.sh

# Open browser to http://localhost:3000
```

See [DOCKER_README.md](DOCKER_README.md) for complete Docker documentation.

## System Architecture

The system consists of three main components:

1. **Audience Service (Port 8000)**: Listens to audience reactions via WebSocket and evaluates if they're laughing using OpenAI's Realtime API
2. **Joke Service (Port 8001)**: Generates jokes and delivers them with native speech using OpenAI's Realtime API
3. **Frontend (Port 3000)**: Debug console with real-time logs and API testing interface

## Implementation Approaches

This project provides **two implementation approaches**:

### 1. Realtime API (Recommended)
- Uses WebSocket connections to OpenAI's Realtime API (`gpt-realtime`)
- Native speech-to-speech with ultra-low latency (~500ms)
- Supports stored prompts with variables
- Real-time audio streaming (PCM16 format)
- Files: `realtime_analyzer.py`, `realtime_generator.py`

### 2. Standard API (Legacy)
- Uses REST API endpoints for chat and TTS
- Separate text generation and speech synthesis
- Higher latency but more flexible
- Files: `analyzer.py`, `generator.py`

## Features

- **Real-time WebSocket Communication**: Low-latency bidirectional streaming
- **Stored Prompt Support**: Use versioned prompts from OpenAI platform
- **Dynamic Joke Generation**: Adapts based on audience feedback
- **Native Speech Output**: Direct audio generation with various voices
- **Adaptive Comedy Style**: Changes based on audience engagement
- **Performance Analytics**: Track engagement and success metrics

## Setup

### Prerequisites

- Python 3.8+
- OpenAI API key

### Installation

1. Clone or navigate to the project directory:
```bash
cd AGI_hackathon
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your OpenAI API key:

**Option A: Using Environment Variable (Recommended)**
```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or on Windows:
```cmd
set OPENAI_API_KEY=your-api-key-here
```

**Option B: Using .env file**
```bash
cp .env.example .env
# Edit .env and add your API key
```

**Option C: Direct in config.yaml**
```yaml
# config.yaml
openai_api_key: "your-actual-api-key-here"
```

The application will check in this order:
1. `config.yaml` file
2. `OPENAI_API_KEY` environment variable

**Verify your setup:**
```bash
python verify_setup.py
```

This will check that everything is configured correctly.

4. (Optional) Configure stored prompts:
```yaml
# In config.yaml
joke_prompt_id: "pmpt_690669c0b07881969bed67ac12c975ff07d719d6a001bd3c"
audience_prompt_id: "pmpt_your_audience_prompt_id"
```

## Usage

### Realtime API Demo (Recommended)

Run the Realtime API demo to see WebSocket-based joke generation:

```bash
python realtime_demo.py
```

This demonstrates:
- WebSocket connection to OpenAI Realtime API
- Real-time joke generation with audio output
- Using stored prompts with variables
- Different audience reaction scenarios

### Basic Usage (Legacy)

Run the stand-up agent with default settings:

```bash
cd src
python main.py
```

### With Custom Configuration

```bash
cd src
python main.py /path/to/custom/config.yaml
```

### Using Stored Prompts

OpenAI's Realtime API supports **stored prompts** - reusable prompt configurations managed on the OpenAI platform.

### Creating a Stored Prompt

1. Go to [OpenAI Prompts](https://platform.openai.com/prompts)
2. Click "Create Prompt"
3. Design your prompt with optional variables using `{{variable_name}}` syntax
4. Save and note the prompt ID (starts with `pmpt_`)

### Example Prompt with Variables

```
You are a {{comedy_style}} stand-up comedian.

The audience is currently {{audience_reaction}}.
Your current theme is: {{theme}}

Generate ONE short, punchy joke (2-4 sentences) that fits the situation.
```

### Using in Code

```yaml
# config.yaml
joke_prompt_id: "pmpt_690669c0b07881969bed67ac12c975ff07d719d6a001bd3c"
```

Variables are automatically passed from the code:
```python
# Variables are populated automatically
session_config["session"]["prompt"] = {
    "id": self.prompt_id,
    "variables": {
        "audience_reaction": {"type": "input_text", "text": "laughing"},
        "comedy_style": {"type": "input_text", "text": "witty"},
        "theme": {"type": "input_text", "text": "AI"}
    }
}
```

### Benefits

- **Version Control**: Update prompts without changing code
- **A/B Testing**: Test different prompt versions
- **Centralized Management**: Manage prompts in one place
- **Template Variables**: Dynamic content injection

## Configuration

Edit `config.yaml` to customize:

- **Comedy style**: Adjust the `comedy_style` and `initial_theme`
- **Voice**: Choose from `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`
- **Performance parameters**: Set `joke_interval`, `max_jokes`, etc.
- **Models**: Configure which OpenAI models to use

## Project Structure

```
AGI_hackathon/
├── src/
│   ├── audience_analyzer/
│   │   ├── __init__.py
│   │   ├── analyzer.py          # Legacy REST API implementation
│   │   └── realtime_analyzer.py # Realtime WebSocket implementation
│   ├── joke_generator/
│   │   ├── __init__.py
│   │   ├── generator.py         # Legacy REST API + TTS
│   │   └── realtime_generator.py # Realtime WebSocket with native speech
│   ├── utils/
│   │   ├── __init__.py
│   │   └── audio_utils.py       # Audio capture/playback utilities
│   └── main.py                  # Main orchestrator (legacy)
├── logs/                        # Log files
├── audio_samples/               # Generated audio files (PCM16 format)
├── config.yaml                  # Configuration file
├── requirements.txt             # Python dependencies
├── realtime_demo.py             # Realtime API demonstration
├── example_usage.py             # Legacy API examples
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore patterns
└── README.md                    # This file
```

## How It Works

### Realtime API Implementation

#### 1. RealtimeAudienceAnalyzer

- Establishes WebSocket connection to `wss://api.openai.com/v1/realtime`
- Streams PCM16 audio chunks to the API
- Receives real-time analysis via event-driven architecture
- Uses `session.update` to configure with stored prompts
- Events: `input_audio_buffer.append`, `response.create`, `response.text.done`

#### 2. RealtimeJokeGenerator

- Connects via WebSocket for bidirectional communication
- Configures session with voice, temperature, and prompt settings
- Sends text prompts via `conversation.item.create`
- Receives both text and audio responses simultaneously
- Events: `response.text.delta`, `response.audio.delta`, `response.done`
- Audio format: PCM16, 16kHz, mono

#### 3. Event Flow

```
1. Connect WebSocket → wss://api.openai.com/v1/realtime?model=gpt-realtime
2. Send session.update → Configure voice, prompt, modalities
3. Send conversation.item.create → User message/prompt
4. Send response.create → Request model response
5. Receive response.audio.delta → Streaming audio chunks
6. Receive response.text.delta → Streaming text
7. Receive response.done → Complete response
```

### Legacy API Implementation

#### 1. AudienceAnalyzer (REST)
- POST requests to `/v1/chat/completions`
- JSON response format
- Separate request per analysis

#### 2. JokeGenerator (REST + TTS)
- POST to `/v1/chat/completions` for text generation
- POST to `/v1/audio/speech` for TTS conversion
- Sequential processing (higher latency)

## API Endpoints Used

### Realtime API (Recommended)

**WebSocket Endpoint:**
```
wss://api.openai.com/v1/realtime?model=gpt-realtime
```

**Headers:**
- `Authorization: Bearer YOUR_API_KEY`
- `OpenAI-Beta: realtime=v1`

**Key Events:**
- `session.update` - Configure session, voice, prompts
- `conversation.item.create` - Add user messages
- `response.create` - Request model response
- `input_audio_buffer.append` - Stream audio input
- `response.audio.delta` - Receive audio output chunks
- `response.text.delta` - Receive text output chunks

### Legacy API Endpoints

**Chat Completions:**
```
POST https://api.openai.com/v1/chat/completions
```

**Text-to-Speech:**
```
POST https://api.openai.com/v1/audio/speech
```

## Example Flow

1. Agent starts performance
2. Audience analyzer evaluates current reaction (e.g., "silent")
3. Joke generator creates a joke to engage the audience
4. Joke is converted to speech using TTS
5. Audio is played/delivered
6. Wait for audience reaction
7. Repeat from step 2

## Future Enhancements

- [ ] Implement real audio capture from microphone
- [ ] Implement real audio playback
- [ ] Add WebSocket support for real-time streaming
- [ ] Add multi-modal audience analysis (visual cues)
- [ ] Implement more sophisticated comedy timing
- [ ] Add support for different comedy styles and personas
- [ ] Create web interface for live performances
- [ ] Add audience interaction capabilities

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
```

### Linting

```bash
flake8 src/
```

## Notes

- The current implementation uses placeholder functions for audio capture and playback
- Audio files are saved to `audio_samples/` directory
- Logs are saved to `logs/standup_agent.log`
- The system requires an active internet connection for OpenAI API calls

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.
