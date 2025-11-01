# OpenAI Realtime API Quick Reference Guide

This guide provides quick reference for using OpenAI's Realtime API with the AI Stand-up Comedy Agent.

## Connection Setup

### WebSocket URL
```
wss://api.openai.com/v1/realtime?model=gpt-realtime
```

### Required Headers
```python
headers = {
    'Authorization': f'Bearer {api_key}',
    'OpenAI-Beta': 'realtime=v1'
}
```

### Python Connection Example
```python
import websockets

ws = await websockets.connect(
    "wss://api.openai.com/v1/realtime?model=gpt-realtime",
    extra_headers=headers
)
```

## Session Configuration

### Basic Session Update
```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "voice": "onyx",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "temperature": 0.8
  }
}
```

### With Stored Prompt
```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "voice": "onyx",
    "prompt": {
      "id": "pmpt_690669c0b07881969bed67ac12c975ff07d719d6a001bd3c",
      "variables": {
        "audience_reaction": {
          "type": "input_text",
          "text": "laughing"
        },
        "comedy_style": {
          "type": "input_text",
          "text": "witty"
        }
      }
    }
  }
}
```

### With Inline Instructions
```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "voice": "onyx",
    "instructions": "You are a stand-up comedian. Generate funny jokes."
  }
}
```

## Common Events

### 1. Send Text Input
```json
{
  "type": "conversation.item.create",
  "item": {
    "type": "message",
    "role": "user",
    "content": [
      {
        "type": "input_text",
        "text": "Tell me a joke about AI"
      }
    ]
  }
}
```

### 2. Send Audio Input
```json
{
  "type": "input_audio_buffer.append",
  "audio": "<base64-encoded-pcm16-audio>"
}
```

### 3. Commit Audio Buffer
```json
{
  "type": "input_audio_buffer.commit"
}
```

### 4. Request Response
```json
{
  "type": "response.create",
  "response": {
    "modalities": ["text", "audio"]
  }
}
```

## Receiving Responses

### Text Response Events
- `response.text.delta` - Streaming text chunks
- `response.text.done` - Complete text response

### Audio Response Events
- `response.audio.delta` - Streaming audio chunks (base64)
- `response.audio.done` - Audio generation complete
- `response.audio_transcript.delta` - Transcript of audio
- `response.audio_transcript.done` - Complete transcript

### Completion Events
- `response.done` - Entire response complete

### Example Event Handling
```python
async for message in websocket:
    event = json.loads(message)
    event_type = event.get('type')

    if event_type == 'response.text.delta':
        text_chunk = event.get('delta', '')
        # Process streaming text

    elif event_type == 'response.audio.delta':
        audio_b64 = event.get('delta', '')
        audio_bytes = base64.b64decode(audio_b64)
        # Process audio chunk

    elif event_type == 'response.done':
        # Response complete
        break
```

## Audio Format Specifications

### Input Audio
- **Format**: PCM16 (Linear PCM, 16-bit signed integer)
- **Sample Rate**: 16,000 Hz
- **Channels**: Mono (1 channel)
- **Encoding**: Base64 for transmission

### Output Audio
- **Format**: PCM16
- **Sample Rate**: 24,000 Hz (default) or configurable
- **Channels**: Mono
- **Encoding**: Base64 in deltas

### Converting Audio to Base64
```python
import base64

# Read PCM16 audio
with open('audio.pcm', 'rb') as f:
    audio_data = f.read()

# Encode to base64
audio_base64 = base64.b64encode(audio_data).decode('utf-8')

# Send to API
event = {
    "type": "input_audio_buffer.append",
    "audio": audio_base64
}
```

### Decoding Audio from Base64
```python
import base64

# Receive from API
audio_base64 = event.get('delta', '')

# Decode from base64
audio_bytes = base64.b64decode(audio_base64)

# Write to file or play
with open('output.pcm', 'wb') as f:
    f.write(audio_bytes)
```

## Available Voices

- `alloy` - Neutral, balanced voice
- `echo` - Clear, articulate voice
- `fable` - Expressive, warm voice
- `onyx` - Deep, authoritative voice (good for comedy)
- `nova` - Energetic, youthful voice
- `shimmer` - Bright, cheerful voice
- `cedar` - (New) Available in Realtime API
- `marin` - (New) Available in Realtime API

## Turn Detection (Server VAD)

Enable automatic turn detection to let the server detect when the user stops speaking:

```json
{
  "type": "session.update",
  "session": {
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "prefix_padding_ms": 300,
      "silence_duration_ms": 500,
      "create_response": true
    }
  }
}
```

**Parameters:**
- `threshold`: Voice activity detection threshold (0.0-1.0)
- `prefix_padding_ms`: Audio before speech to include
- `silence_duration_ms`: Silence duration to mark turn end
- `create_response`: Auto-create response on turn end

## Error Handling

### Error Event
```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "code": "invalid_value",
    "message": "Description of the error",
    "param": "session.voice"
  }
}
```

### Common Errors
- `invalid_request_error` - Invalid request format
- `authentication_error` - Invalid API key
- `rate_limit_error` - Too many requests
- `server_error` - OpenAI server error

## Best Practices

1. **Connection Management**
   - Implement reconnection logic for dropped connections
   - Handle connection timeouts gracefully
   - Close connections properly when done

2. **Audio Streaming**
   - Send audio in small chunks (e.g., 100ms chunks)
   - Don't exceed 15 MiB per audio buffer append
   - Monitor buffer state to avoid overflow

3. **Response Handling**
   - Always handle all event types
   - Implement timeout for response collection
   - Buffer audio chunks for smooth playback

4. **Error Recovery**
   - Log all errors for debugging
   - Implement fallback responses
   - Retry failed connections with backoff

5. **Performance**
   - Use WebRTC instead of WebSocket for browser clients
   - Minimize latency with appropriate chunk sizes
   - Consider caching for repeated prompts

## Stored Prompt Variables

### Variable Format
Variables must use this structure:
```json
{
  "variable_name": {
    "type": "input_text",
    "text": "actual value"
  }
}
```

### Example with Multiple Variables
```json
{
  "prompt": {
    "id": "pmpt_abc123",
    "variables": {
      "user_name": {"type": "input_text", "text": "Alice"},
      "topic": {"type": "input_text", "text": "machine learning"},
      "style": {"type": "input_text", "text": "humorous"}
    }
  }
}
```

## Pricing (as of 2025)

**gpt-realtime Model:**
- Audio input: $32 / 1M tokens ($0.40 cached)
- Audio output: $64 / 1M tokens
- Text input: ~$2.50 / 1M tokens
- Text output: ~$10 / 1M tokens

**Note:** Prices are 20% lower than previous gpt-4o-realtime-preview

## Resources

- [Official Realtime API Docs](https://platform.openai.com/docs/guides/realtime)
- [API Reference](https://platform.openai.com/docs/api-reference/realtime)
- [Stored Prompts](https://platform.openai.com/prompts)
- [Community Forum](https://community.openai.com)

## Example: Complete Flow

```python
import asyncio
import websockets
import json
import base64

async def demo():
    # 1. Connect
    ws = await websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-realtime",
        extra_headers={
            'Authorization': f'Bearer {api_key}',
            'OpenAI-Beta': 'realtime=v1'
        }
    )

    # 2. Configure session
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "voice": "onyx"
        }
    }))

    # 3. Send message
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Tell a joke"}]
        }
    }))

    # 4. Request response
    await ws.send(json.dumps({
        "type": "response.create",
        "response": {"modalities": ["text", "audio"]}
    }))

    # 5. Collect response
    audio_chunks = []
    async for message in ws:
        event = json.loads(message)

        if event['type'] == 'response.audio.delta':
            audio_chunks.append(base64.b64decode(event['delta']))
        elif event['type'] == 'response.done':
            break

    # 6. Process audio
    full_audio = b''.join(audio_chunks)

    # 7. Close
    await ws.close()

asyncio.run(demo())
```
