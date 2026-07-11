# Vocal Bridge Developer Guide

Everything you need to integrate voice agents into your application.

---

## Overview

Vocal Bridge provides voice AI agents that you can integrate into any application using WebRTC. Your users can have real-time voice conversations with AI agents through web browsers, mobile apps, or any platform that supports WebRTC.

| Feature | Description |
|---------|-------------|
| Real-time Voice | Sub-second latency voice AI using WebRTC |
| Secure API Keys | Production-ready authentication |
| Multi-platform | JavaScript, Python, React, Flutter, and more |

---

## Quick Start

Get your voice agent working in 3 steps:

### 1. Create an API Key

Go to your agent's page, open Developer Mode, and click "Create API Key" in the API Keys section.

### 2. Generate a Token (Server-side)

Call the token endpoint from your backend to get a LiveKit access token.

```bash
curl -X POST "http://vocalbridgeai.com/api/v1/token" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"participant_name": "User"}'
```

### 3. Connect from Your Client

Use the LiveKit SDK to connect and enable the microphone.

```javascript
import { Room } from 'livekit-client';

const room = new Room();
await room.connect(livekit_url, token);
await room.localParticipant.setMicrophoneEnabled(true);
```

---

## Authentication

Vocal Bridge uses API keys for authentication. API keys allow your backend server to generate access tokens without requiring user login.

> **Security:** Never expose your API key in client-side code. Always call the token endpoint from your backend server.

### API Key Format

API keys start with `vb_` followed by a secure random string:

```
vb_abc123def456...
```

### Using API Keys

Include your API key in requests using either method:

```bash
# Option 1: X-API-Key header (recommended)
curl -H "X-API-Key: vb_your_api_key" http://vocalbridgeai.com/api/v1/token

# Option 2: Authorization header
curl -H "Authorization: Bearer vb_your_api_key" http://vocalbridgeai.com/api/v1/token
```

### Account-Level API Keys

Account-level API keys work across all your agents. When using an account-level key, you must include the `X-Agent-Id` header to specify which agent to target:

```bash
# Account-level key: include X-Agent-Id header
curl -H "X-API-Key: vb_your_account_key" \
     -H "X-Agent-Id: your-agent-uuid" \
     http://vocalbridgeai.com/api/v1/token
```

Agent-scoped API keys do not require this header — the agent is determined automatically from the key.

---

## API Reference

### POST `/api/v1/token`

Generate a LiveKit access token for connecting to the agent.

#### Request Headers

| Header | Description |
|--------|-------------|
| X-API-Key | Your API key (required) |
| X-Agent-Id | Agent UUID (required for account-level API keys) |
| Content-Type | application/json |

#### Request Body (optional)

| Field | Type | Description |
|-------|------|-------------|
| participant_name | string | Display name for the participant (default: "API Client") |
| session_id | string | Custom session ID (default: auto-generated) |

#### Response

```json
{
  "livekit_url": "wss://tutor-j7bhwjbm.livekit.cloud",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "room_name": "user-abc-agent-xyz-api-12345",
  "participant_identity": "api-client-xxxx-12345",
  "expires_in": 3600,
  "agent_mode": "cascaded_concierge"
}
```

### GET `/api/v1/agent`

Get information about the agent associated with your API key.

#### Response

```json
{
  "id": "uuid",
  "name": "My Voice Agent",
  "mode": "cascaded_concierge",
  "deployment_status": "active",
  "phone_number": "+1234567890",
  "greeting": "Hello! How can I help you?",
  "background_enabled": true,
  "hold_enabled": false,
  "hangup_enabled": false,
  "created_at": "2025-01-14T12:00:00Z"
}
```

---

## JavaScript SDK

Use the [LiveKit JavaScript SDK](https://docs.livekit.io/client-sdk-js/) to connect from web browsers.

### Installation

```bash
npm install livekit-client
```

### Complete Example

```javascript
import { Room, RoomEvent, Track } from 'livekit-client';

class VoiceAgent {
  constructor() {
    this.room = new Room();
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    // Handle incoming audio from the agent
    this.room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind === Track.Kind.Audio) {
        const audioElement = track.attach();
        document.body.appendChild(audioElement);
        console.log('Agent audio connected');
      }
    });

    // Handle connection state changes
    this.room.on(RoomEvent.ConnectionStateChanged, (state) => {
      console.log('Connection state:', state);
    });

    // Handle disconnection
    this.room.on(RoomEvent.Disconnected, () => {
      console.log('Disconnected from room');
    });
  }

  async connect() {
    // Get token from your backend
    const response = await fetch('/api/voice-token');
    const { livekit_url, token } = await response.json();

    // Connect to the room
    await this.room.connect(livekit_url, token);
    console.log('Connected to room:', this.room.name);

    // Enable microphone
    await this.room.localParticipant.setMicrophoneEnabled(true);
    console.log('Microphone enabled - start speaking!');
  }

  async disconnect() {
    await this.room.disconnect();
  }
}

// Usage
const agent = new VoiceAgent();
await agent.connect();
```

### Backend Token Endpoint (Node.js/Express)

```javascript
// server.js
const express = require('express');
const app = express();

const VOCAL_BRIDGE_API_KEY = process.env.VOCAL_BRIDGE_API_KEY;
const VOCAL_BRIDGE_URL = 'http://vocalbridgeai.com';

app.get('/api/voice-token', async (req, res) => {
  try {
    const response = await fetch(`${VOCAL_BRIDGE_URL}/api/v1/token`, {
      method: 'POST',
      headers: {
        'X-API-Key': VOCAL_BRIDGE_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        participant_name: req.user?.name || 'User'
      })
    });

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('Failed to get token:', error);
    res.status(500).json({ error: 'Failed to get voice token' });
  }
});

app.listen(3000);
```

---

## Python SDK

Use the [LiveKit Python SDK](https://docs.livekit.io/client-sdk-python/) for server-side or desktop applications.

### Installation

```bash
pip install livekit requests
```

### Complete Example

```python
import asyncio
import os
import requests
from livekit import rtc

VOCAL_BRIDGE_API_KEY = os.environ.get('VOCAL_BRIDGE_API_KEY')
VOCAL_BRIDGE_URL = 'http://vocalbridgeai.com'

def get_voice_token(participant_name: str = 'Python Client'):
    """Get a voice token from Vocal Bridge API."""
    response = requests.post(
        f'{VOCAL_BRIDGE_URL}/api/v1/token',
        headers={
            'X-API-Key': VOCAL_BRIDGE_API_KEY,
            'Content-Type': 'application/json'
        },
        json={'participant_name': participant_name}
    )
    response.raise_for_status()
    return response.json()

async def main():
    # Get token
    token_data = get_voice_token()
    print(f"Connecting to room: {token_data['room_name']}")

    # Create room
    room = rtc.Room()

    # Set up event handlers
    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print("Agent audio connected!")
            audio_stream = rtc.AudioStream(track)

    @room.on("disconnected")
    def on_disconnected():
        print("Disconnected from room")

    # Connect
    await room.connect(token_data['livekit_url'], token_data['token'])
    print(f"Connected! Room: {room.name}")

    # Publish microphone
    source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    await room.local_participant.publish_track(track)
    print("Microphone enabled - start speaking!")

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await room.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
```

### Flask Backend Example

```python
# app.py
from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

VOCAL_BRIDGE_API_KEY = os.environ.get('VOCAL_BRIDGE_API_KEY')
VOCAL_BRIDGE_URL = 'http://vocalbridgeai.com'

@app.route('/api/voice-token')
def get_voice_token():
    response = requests.post(
        f'{VOCAL_BRIDGE_URL}/api/v1/token',
        headers={
            'X-API-Key': VOCAL_BRIDGE_API_KEY,
            'Content-Type': 'application/json'
        },
        json={'participant_name': 'Web User'}
    )
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(port=5000)
```

---

## React Integration

Use the [LiveKit React Components](https://docs.livekit.io/reference/components/react/) for easy integration with React applications.

Use the same backend token endpoint from the JavaScript SDK section to get LiveKit tokens.

### Installation

```bash
npm install @livekit/components-react livekit-client
```

### React Hook Example

```typescript
// useVoiceAgent.ts
import { useState, useCallback, useEffect } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';

interface VoiceAgentState {
  isConnected: boolean;
  isConnecting: boolean;
  isMicEnabled: boolean;
  error: string | null;
}

export function useVoiceAgent() {
  const [room] = useState(() => new Room());
  const [state, setState] = useState<VoiceAgentState>({
    isConnected: false,
    isConnecting: false,
    isMicEnabled: false,
    error: null
  });

  useEffect(() => {
    const handleTrackSubscribed = (track: any) => {
      if (track.kind === Track.Kind.Audio) {
        const audioEl = track.attach();
        document.body.appendChild(audioEl);
      }
    };

    const handleDisconnected = () => {
      setState(s => ({ ...s, isConnected: false, isMicEnabled: false }));
    };

    room.on(RoomEvent.TrackSubscribed, handleTrackSubscribed);
    room.on(RoomEvent.Disconnected, handleDisconnected);

    return () => {
      room.off(RoomEvent.TrackSubscribed, handleTrackSubscribed);
      room.off(RoomEvent.Disconnected, handleDisconnected);
      room.disconnect();
    };
  }, [room]);

  const connect = useCallback(async () => {
    setState(s => ({ ...s, isConnecting: true, error: null }));

    try {
      const res = await fetch('/api/voice-token');
      const { livekit_url, token } = await res.json();

      await room.connect(livekit_url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      setState(s => ({
        ...s,
        isConnected: true,
        isConnecting: false,
        isMicEnabled: true
      }));
    } catch (err) {
      setState(s => ({
        ...s,
        isConnecting: false,
        error: err instanceof Error ? err.message : 'Connection failed'
      }));
    }
  }, [room]);

  const disconnect = useCallback(async () => {
    await room.disconnect();
  }, [room]);

  const toggleMic = useCallback(async () => {
    const enabled = !state.isMicEnabled;
    await room.localParticipant.setMicrophoneEnabled(enabled);
    setState(s => ({ ...s, isMicEnabled: enabled }));
  }, [room, state.isMicEnabled]);

  return { ...state, connect, disconnect, toggleMic };
}
```

### Handling Client Actions (React)

```typescript
// Add to useVoiceAgent hook for bidirectional communication
import { RoomEvent } from 'livekit-client';

// Handle actions FROM the agent (Agent to App)
useEffect(() => {
  const handleData = (
    payload: Uint8Array,
    participant: any,
    kind: any,
    topic?: string
  ) => {
    if (topic === 'client_actions') {
      const data = JSON.parse(new TextDecoder().decode(payload));
      if (data.type === 'client_action') {
        handleAgentAction(data.action, data.payload);
      }
    }
  };

  room.on(RoomEvent.DataReceived, handleData);
  return () => { room.off(RoomEvent.DataReceived, handleData); };
}, [room]);

function handleAgentAction(action: string, payload: any) {
  switch (action) {
    case 'navigate':
      window.location.href = payload.url;
      break;
    case 'show_product':
      setProductId(payload.productId);
      break;
    default:
      console.log('Unknown action:', action, payload);
  }
}

// Send actions TO the agent (App to Agent)
const sendActionToAgent = useCallback(async (
  action: string,
  payload: Record<string, any> = {}
) => {
  const message = JSON.stringify({
    type: 'client_action',
    action,
    payload
  });
  await room.localParticipant.publishData(
    new TextEncoder().encode(message),
    { reliable: true, topic: 'client_actions' }
  );
}, [room]);
```

### Next.js API Route Example

Create `app/api/voice-token/route.ts`:

```typescript
// app/api/voice-token/route.ts (Next.js App Router)
import { NextResponse } from 'next/server';

const VOCAL_BRIDGE_API_KEY = process.env.VOCAL_BRIDGE_API_KEY!;
const VOCAL_BRIDGE_URL = 'http://vocalbridgeai.com';

export async function GET() {
  try {
    const response = await fetch(`${VOCAL_BRIDGE_URL}/api/v1/token`, {
      method: 'POST',
      headers: {
        'X-API-Key': VOCAL_BRIDGE_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        participant_name: 'Web User',
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to get token');
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to get voice token' },
      { status: 500 }
    );
  }
}
```

---

## Flutter SDK

Use the [LiveKit Flutter SDK](https://docs.livekit.io/client-sdk-flutter/) to build voice-enabled mobile apps for iOS and Android.

### Installation

Add to your `pubspec.yaml`:

```yaml
dependencies:
  livekit_client: ^2.3.0
  http: ^1.2.0
```

### Complete Example

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:livekit_client/livekit_client.dart';

class VoiceAgentService {
  Room? _room;
  EventsListener<RoomEvent>? _listener;

  Future<Map<String, dynamic>> _getTokenFromBackend() async {
    final response = await http.get(
      Uri.parse('https://your-backend.com/api/voice-token'),
    );
    return jsonDecode(response.body);
  }

  Future<void> connect() async {
    final tokenData = await _getTokenFromBackend();
    final livekitUrl = tokenData['livekit_url'] as String;
    final token = tokenData['token'] as String;

    _room = Room();

    _listener = _room!.createListener();
    _listener!.on<TrackSubscribedEvent>((event) {
      if (event.track.kind == TrackType.AUDIO) {
        print('Agent audio track subscribed');
      }
    });

    _listener!.on<RoomDisconnectedEvent>((event) {
      print('Disconnected from room');
    });

    await _room!.connect(livekitUrl, token);
    print('Connected to room: ${_room!.name}');

    await _room!.localParticipant?.setMicrophoneEnabled(true);
    print('Microphone enabled - start speaking!');
  }

  Future<void> disconnect() async {
    await _room?.disconnect();
    _room = null;
    _listener = null;
  }

  bool get isConnected => _room?.connectionState == ConnectionState.connected;
}
```

### Handling Client Actions (Flutter)

```dart
// Add to VoiceAgentService class

void _setupClientActionHandler() {
  _listener!.on<DataReceivedEvent>((event) {
    if (event.topic == 'client_actions') {
      final data = jsonDecode(utf8.decode(event.data));
      if (data['type'] == 'client_action') {
        _handleAgentAction(data['action'], data['payload']);
      }
    }
  });
}

void _handleAgentAction(String action, Map<String, dynamic> payload) {
  switch (action) {
    case 'navigate':
      print('Navigate to: ${payload['screen']}');
      break;
    case 'show_product':
      print('Show product: ${payload['productId']}');
      break;
    default:
      print('Unknown action: $action');
  }
}

Future<void> sendActionToAgent(String action, [Map<String, dynamic>? payload]) async {
  final message = jsonEncode({
    'type': 'client_action',
    'action': action,
    'payload': payload ?? {},
  });
  await _room?.localParticipant?.publishData(
    utf8.encode(message),
    reliable: true,
    topic: 'client_actions',
  );
}
```

### Platform Setup

#### iOS Configuration

Add to `ios/Runner/Info.plist`:

```xml
<key>NSMicrophoneUsageDescription</key>
<string>This app needs microphone access for voice chat</string>
<key>UIBackgroundModes</key>
<array>
  <string>audio</string>
</array>
```

#### Android Configuration

Add to `android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS"/>
```

---

## Client Actions

Client Actions enable bidirectional communication between your voice agent and your client application via LiveKit's data channel.

### Directions

- **Agent to App**: The agent triggers actions in your client (e.g., navigate to a page, show a product card, update the UI).
- **App to Agent**: Your client sends events to the agent (e.g., user clicked a button, form submitted, data loaded).

### Behavior (App to Agent)

Each `app_to_agent` action has a `behavior` that controls how the agent handles the inbound event:

- **respond** (default): The agent generates a reply when this event arrives. Use for events that require the agent to speak.
- **notify**: The event is silently added to conversation context. The agent sees it on its next turn but does *not* reply immediately. Use for informational updates.

This prevents feedback loops where an agent action triggers a client event which triggers another agent reply, and so on.

### How It Works

#### Agent to App (Outbound)

1. Agent decides to trigger an action during conversation
2. Agent calls `trigger_client_action`
3. Action is published to LiveKit data channel
4. Your app receives and handles it

#### App to Agent (Inbound)

1. Your app publishes data to LiveKit
2. Agent receives and validates the event
3. Behavior is checked: **respond** or **notify**
4. Agent replies or silently absorbs the event

### Receiving Actions from Agent (JavaScript)

```javascript
import { Room, RoomEvent } from 'livekit-client';

const room = new Room();

room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
  if (topic === 'client_actions') {
    const data = JSON.parse(new TextDecoder().decode(payload));
    if (data.type === 'client_action') {
      handleAgentAction(data.action, data.payload);
    }
  }
});

function handleAgentAction(action, payload) {
  switch (action) {
    case 'navigate':
      window.location.href = payload.url;
      break;
    case 'show_product':
      showProductModal(payload.product_id);
      break;
    default:
      console.log('Unknown action:', action, payload);
  }
}
```

### Sending Actions to Agent (JavaScript)

```javascript
function sendActionToAgent(action, payload = {}) {
  const message = JSON.stringify({
    type: 'client_action',
    action: action,
    payload: payload
  });
  room.localParticipant.publishData(
    new TextEncoder().encode(message),
    { reliable: true, topic: 'client_actions' }
  );
}

// Example: User clicked buy (behavior: respond - agent will reply)
sendActionToAgent('user_clicked_buy', { productId: '123', quantity: 2 });

// Example: Practice result (behavior: notify - agent absorbs silently)
sendActionToAgent('practice_result', { score: 95, word: 'hello' });
```

### Example Configuration

| Action Name | Direction | Behavior | Description |
|-------------|-----------|----------|-------------|
| show_product | agent_to_app | — | Display product details in the app |
| user_clicked_buy | app_to_agent | respond | User clicked the buy button |
| practice_result | app_to_agent | notify | User completed a practice exercise |

### Configure via CLI

```bash
# Set client actions from file
vb config set --client-actions-file client_actions.json

# Example client_actions.json:
# [
#   {"name": "show_product", "description": "Display a product card", "direction": "agent_to_app"},
#   {"name": "user_clicked_buy", "description": "User clicked buy", "direction": "app_to_agent", "behavior": "respond"},
#   {"name": "practice_result", "description": "Practice completed", "direction": "app_to_agent", "behavior": "notify"}
# ]
```

---

## Live Transcript (Built-in)

All Vocal Bridge agents automatically send a `send_transcript` event whenever the user speaks or the agent responds. This is a built-in protocol-level feature that works independently of any configured client actions — no setup required.

### Transcript Message Format

```json
{
  "type": "client_action",
  "action": "send_transcript",
  "payload": {
    "role": "user",
    "text": "Hello, how are you?",
    "timestamp": 1708123456789
  }
}
```

### Subscribing to Transcript (JavaScript)

```javascript
const transcript = [];

room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
  if (topic === 'client_actions') {
    const data = JSON.parse(new TextDecoder().decode(payload));
    if (data.type === 'client_action' && data.action === 'send_transcript') {
      const { role, text, timestamp } = data.payload;
      transcript.push({ role, text, timestamp });
      updateTranscriptUI(role, text);
    }
  }
});
```

### React Example

```typescript
import { useState, useEffect } from 'react';
import { RoomEvent } from 'livekit-client';

function useTranscript(room) {
  const [transcript, setTranscript] = useState([]);

  useEffect(() => {
    const handleData = (payload, participant, kind, topic) => {
      if (topic === 'client_actions') {
        const data = JSON.parse(new TextDecoder().decode(payload));
        if (data.type === 'client_action' && data.action === 'send_transcript') {
          setTranscript(prev => [...prev, data.payload]);
        }
      }
    };
    room.on(RoomEvent.DataReceived, handleData);
    return () => room.off(RoomEvent.DataReceived, handleData);
  }, [room]);

  return transcript;
}
```

### Flutter Example

```dart
import 'dart:convert';
import 'package:livekit_client/livekit_client.dart';

class TranscriptEntry {
  final String role;
  final String text;
  final int timestamp;
  TranscriptEntry({required this.role, required this.text, required this.timestamp});
}

// In your room setup:
final transcript = <TranscriptEntry>[];

listener.on<DataReceivedEvent>((event) {
  if (event.topic == 'client_actions') {
    final data = jsonDecode(utf8.decode(event.data));
    if (data['type'] == 'client_action' && data['action'] == 'send_transcript') {
      final payload = data['payload'];
      transcript.add(TranscriptEntry(
        role: payload['role'],
        text: payload['text'],
        timestamp: payload['timestamp'],
      ));
    }
  }
});
```

### How It Works

- Transcript events are sent on the same `client_actions` data channel topic as heartbeat and client actions
- User transcripts are sent when speech-to-text produces a final transcription
- Agent transcripts are sent when the agent produces a response
- No configuration needed — this is automatic for all agents

---

## MCP Tools

The Model Context Protocol (MCP) allows your voice agent to connect to external tools and services. By providing an MCP server URL, your agent gains access to calendars, email, CRM systems, databases, and thousands of other integrations.

### Quick Setup with Zapier

The easiest way to add tools is through [Zapier MCP](https://zapier.com/mcp). Connect 7,000+ apps to your voice agent in minutes.

### How MCP Works

1. Obtain an MCP server URL from Zapier or your own MCP server
2. Add the URL in your agent's configuration
3. The agent automatically discovers and loads available tools
4. During conversations, the agent can call these tools to fetch data or perform actions

### Example Use Cases

| Use Case | Description |
|----------|-------------|
| Calendar Integration | Check availability, book appointments, send meeting invites via Google Calendar or Outlook |
| CRM Access | Look up customer info, create leads, update contact records in Salesforce, HubSpot, etc. |
| Email & Messaging | Send emails, Slack messages, or SMS notifications during or after calls |
| Database Queries | Query product catalogs, inventory, order status, or any custom database |

### Getting an MCP Server URL

**Option 1: Zapier MCP (Recommended)**

1. Go to [zapier.com/mcp](https://zapier.com/mcp)
2. Sign in and configure the apps you want to connect
3. Copy your MCP server URL (format: `https://actions.zapier.com/mcp/...`)
4. Paste into your agent's MCP Server URL field

**Option 2: Custom MCP Server**

Build your own MCP server using the [MCP specification](https://modelcontextprotocol.io). Your server must support the Streamable HTTP transport.

---

## Custom HTTP API Tools

Custom HTTP API tools let your agent call external REST APIs during conversations. The agent can fetch data, submit forms, trigger webhooks, or interact with any HTTPS endpoint. Tools run in the background and results are spoken back to the caller.

### How It Works

1. Configure one or more API tools with URL, method, authentication, and parameters
2. During a conversation, the agent decides when to call a tool based on the user's request
3. The agent constructs the HTTP request, injects authentication, and calls the endpoint
4. The response is parsed and the agent speaks the result to the caller

### Supported Features

| Feature | Details |
|---------|---------|
| HTTP Methods | GET, POST, PUT, DELETE, PATCH |
| Authentication | Bearer token, Basic auth, Custom header, Query parameter, or None |
| Parameters | Query params, path params, and request body. Types: string, number, boolean |
| Reliability | Configurable timeout (1–300s) and retry count (0–5). Auto-retry on server errors |

### Example Configuration

```json
[
  {
    "id": "1",
    "name": "get_weather",
    "description": "Get the current weather for a city",
    "method": "GET",
    "url": "https://api.weather.com/v1/current",
    "auth": {
      "type": "bearer",
      "credentials": { "token": "your-api-key" }
    },
    "parameters": [
      {
        "name": "city",
        "type": "string",
        "description": "City name",
        "required": true,
        "location": "query"
      }
    ],
    "timeout": 30,
    "max_retries": 2,
    "enabled": true
  }
]
```

### Authentication Types

| Type | Credentials | Behavior |
|------|-------------|----------|
| `bearer` | `{"token": "sk-xxx"}` | Sends `Authorization: Bearer sk-xxx` |
| `basic` | `{"username": "u", "password": "p"}` | Sends Base64-encoded Basic auth header |
| `header` | `{"header_name": "X-Key", "header_value": "val"}` | Sends a custom HTTP header |
| `query` | `{"param_name": "key", "param_value": "val"}` | Appends a query parameter to the URL |
| `none` | N/A | No authentication |

### Configure via CLI

```bash
# Set API tools from file
vb config set --api-tools-file api_tools.json

# Clear all API tools
vb config set --api-tools-file /dev/stdin <<< '[]'

# View current tools
vb config show
```

### Limits

- Maximum **20 tools** per agent
- Tool names must be unique, start with a letter, and contain only letters, numbers, and underscores
- URLs must use **HTTPS** only
- Credentials are **encrypted at rest**

---

## Post-Processing

Post-processing runs automatically after each call ends. Use it to summarize conversations, update CRM records, send follow-up emails, create tickets, or trigger any workflow based on what happened during the call.

### Automatic Execution

Post-processing runs in the background after every call. No user action required. The transcript and call metadata are automatically available.

### How It Works

1. Call ends (user hangs up or agent ends the call)
2. Full conversation transcript is captured
3. Post-processing LLM analyzes the transcript using your custom prompt
4. If MCP tools are configured, the LLM can call them to perform actions
5. Results are logged for review

### Configuration Options

#### Post-Processing Prompt

Tell the LLM what to do with the conversation transcript. Be specific about the output format and actions to take.

Example: "Analyze this call transcript and: 1) Create a brief summary (2-3 sentences), 2) Extract any action items mentioned, 3) Identify the caller's sentiment (positive/neutral/negative), 4) If the caller requested a callback, create a task in the CRM."

#### Post-Processing MCP Server

Optionally connect a separate MCP server specifically for post-processing tasks. This allows the post-processing LLM to update CRMs, send emails, create tickets, or trigger any automation after the call.

### Example Use Cases

| Use Case | Description |
|----------|-------------|
| Call Summaries | Generate structured summaries with key points, decisions, and next steps |
| CRM Updates | Automatically log call notes, update lead status, or create follow-up tasks |
| Follow-up Emails | Send personalized follow-up emails based on the conversation content |
| Escalation Alerts | Detect urgent issues and notify team members via Slack, email, or SMS |

### Available Context

| Context | Description |
|---------|-------------|
| Full transcript | Complete conversation with speaker labels |
| Call duration | How long the call lasted |
| Timestamp | When the call started and ended |
| Agent configuration | The agent's system prompt and settings |
| MCP tools | Any tools configured for post-processing |

---

## AI Agents

Connect your existing AI agent to a Vocal Bridge voice agent. The voice agent handles conversation flow, greetings, and filler while delegating domain-specific questions to your agent via the client-side data channel.

### How It Works

1. User asks a domain-specific question
2. Voice agent sends a `query_agent` action via the data channel
3. Your app receives the query and forwards it to your AI agent
4. Your app sends the response back via `agent_response` action
5. Voice agent speaks the response to the user

### Data Channel Protocol

**Query from voice agent (Agent to App):**

```json
{
  "type": "client_action",
  "action": "query_agent",
  "payload": { "query": "What appointments do I have?", "turn_id": "abc123" }
}
```

**Response from your agent (App to Agent):**

```json
{
  "type": "client_action",
  "action": "agent_response",
  "payload": { "response": "You have a dentist at 10am.", "turn_id": "abc123" }
}
```

### JavaScript Integration

```javascript
room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
  if (topic === 'client_actions') {
    const data = JSON.parse(new TextDecoder().decode(payload));
    if (data.type === 'client_action' && data.action === 'query_agent') {
      const { query, turn_id } = data.payload;
      // Forward to your AI agent
      callYourAgent(query).then(response => {
        room.localParticipant.publishData(
          new TextEncoder().encode(JSON.stringify({
            type: 'client_action',
            action: 'agent_response',
            payload: { response, turn_id }
          })),
          { reliable: true, topic: 'client_actions' }
        );
      });
    }
  }
});
```

### Configure via CLI

```bash
# Enable with inline flags
vb config set --ai-agent-enabled true --ai-agent-description "Customer support agent"

# Or set from a JSON file
vb config set --ai-agent-file ai_agent.json

# Disable
vb config set --ai-agent-enabled false

# View current config
vb config show
```

### Configuration

```json
{
  "enabled": true,
  "description": "Customer support agent for Acme Corp",
  "verbatim": false
}
```

- **enabled** — Whether AI Agent integration is active
- **description** — What your agent does (max 2000 chars). Guides the voice agent on when to delegate.
- **verbatim** — If true, speaks responses exactly as received. If false (default), adapts for natural voice delivery.

### Notes

- The voice agent fills naturally while waiting for your agent's response (same as background AI)
- Timeout is 60 seconds — if your agent doesn't respond, the voice agent answers from its own knowledge
- Works with web deploy targets only (requires data channel)

---

## Troubleshooting

### Connection fails with "403 Forbidden"

Your API key may be invalid or revoked. Check that you're using the correct API key and that it hasn't been revoked in the dashboard.

### No audio from the agent

Make sure you're attaching the audio track to an audio element when it's subscribed. Also check that the audio element is not muted and that the browser has autoplay permissions.

```javascript
room.on(RoomEvent.TrackSubscribed, (track) => {
  if (track.kind === 'audio') {
    const audioEl = track.attach();
    audioEl.play(); // May need user gesture first
    document.body.appendChild(audioEl);
  }
});
```

### Microphone not working

The browser may not have microphone permissions. Request permission before calling `setMicrophoneEnabled(true)`:

```javascript
// Request microphone permission first
await navigator.mediaDevices.getUserMedia({ audio: true });

// Then enable in LiveKit
await room.localParticipant.setMicrophoneEnabled(true);
```

### Token expired

Tokens are valid for 1 hour. If you get a token expiration error, request a new token from your backend and reconnect.

### CORS errors

Don't call the Vocal Bridge API directly from the browser. Instead, make requests from your backend server to avoid CORS issues and keep your API key secure.

---

## CLI

The `vb` CLI lets you manage voice agents from the terminal. View call logs, update prompts, stream debug events, and iterate on your agent without opening the dashboard.

### Installation

```bash
pip install vocal-bridge
```

Requires Python 3.9+. Includes WebSocket support for real-time debug streaming.

### Authentication

```bash
# Interactive login
vb auth login

# Or provide key directly
vb auth login vb_your_api_key_here

# For account keys, select an agent after login
vb agent use

# Check status
vb auth status
```

### Commands

| Command | Description |
|---------|-------------|
| `vb agent` | Show current agent info |
| `vb agent list` | List all agents |
| `vb agent use` | Select an agent to work with |
| `vb agent create` | Create and deploy a new agent (Pilot only) |
| `vb logs` | List recent call logs |
| `vb logs show <id>` | View call details and transcript |
| `vb logs download <id>` | Download call recording |
| `vb stats` | Show call statistics |
| `vb prompt show` | View current prompt and greeting |
| `vb prompt edit` | Edit prompt in $EDITOR |
| `vb prompt set --file` | Set prompt from file or stdin |
| `vb config show` | View all agent settings |
| `vb config get <section>` | Export a config section as JSON |
| `vb config edit` | Edit full config in $EDITOR (JSON) |
| `vb config set` | Update individual settings |
| `vb config options` | Discover valid values for settings |
| `vb call <phone>` | Place an outbound call (Pilot only) |
| `vb debug` | Stream real-time debug events |
| `vb docs` | Get developer integration docs |

### Discover Valid Options

```bash
# Show all available options
vb config options

# Show options for a specific setting
vb config options voice
vb config options "TTS Model"
vb config options language

# Show all settings in a category
vb config options stt
vb config options audio
```

### Update Settings

```bash
# Change agent style
vb config set --style Chatty

# Enable capabilities
vb config set --debug-mode true
vb config set --hold-enabled true

# Set session limits
vb config set --max-call-duration 15
vb config set --max-history-messages 50

# Set integrations from files
vb config set --mcp-servers-file servers.json
vb config set --client-actions-file actions.json
vb config set --api-tools-file tools.json
```

### Export & Update Settings (Roundtrip)

```bash
# Export a config section as JSON
vb config get model-settings
vb config get client-actions
vb config get mcp-servers
vb config get api-tools
vb config get ai-agent
vb config get builtin-tools

# Roundtrip: export, edit, and re-apply
vb config get model-settings > settings.json
# edit settings.json...
vb config set --model-settings-file settings.json

# Partial update: change only specific fields with --merge
echo '{"realtime": {"model": "gpt-realtime-1.5"}}' > update.json
vb config set --model-settings-file update.json --merge
```

### Example Workflow

```bash
# 1. Check current agent setup
vb agent
vb prompt show

# 2. Make some test calls to your agent...

# 3. Review call logs
vb logs
vb logs show <session_id>

# 4. Download a recording for analysis
vb logs download <session_id>

# 5. Update the prompt based on findings
vb prompt edit

# 6. Check statistics
vb stats
```

### Environment Variables

```bash
export VOCAL_BRIDGE_API_KEY=vb_your_api_key_here
export VOCAL_BRIDGE_API_URL=https://vocalbridgeai.com  # optional
```

### Troubleshooting

#### "No API key found"

Run `vb auth login` or set the `VOCAL_BRIDGE_API_KEY` environment variable.

#### "Invalid API key"

Check that your key starts with `vb_` and hasn't been revoked. Generate a new key if needed.

#### "Agent not found"

The API key may have been created for a deleted agent. Create a new key from an active agent.

### Links

- [CLI on PyPI](https://pypi.org/project/vocal-bridge/)

---

