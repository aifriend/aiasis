# AIASIS - Blueprint

> In-ear personal AI assistant that listens continuously through AirPods, reasons about what it hears, and whispers insights back to the user.

---

## 1. Market Context

Existing products like Omi, Limitless, Bee, and Tab/Friend focus on memory capture or companionship, but **none closes the full loop**: listen -> reason deeply -> respond with enriched voice for general use. That is the gap aiasis aims to fill.

### Strategic Positioning

- **The moat is timing quality, not model quality.** Any team can call STT/LLM/TTS APIs. The defensible layer is deciding *when* to whisper and how intrusive it should feel in real life.
- **Async reasoning is a positioning advantage.** Most voice assistants optimize for instant responses. aiasis should explicitly position "deeper delayed insight" as a different category.
- **Trust UX is a hard requirement, not a feature.** If users or bystanders feel covertly recorded, adoption collapses even if insights are excellent.

One-line narrative:
> "AIASIS listens continuously, thinks deeply in the background, and whispers only the insight that changes your next decision."

### MVP Use Case: Meeting Coaching

V1 targets a single scenario: **real-time meeting coaching**. The user wears AirPods in a work meeting; after every N minutes of conversation, aiasis whispers a brief coaching insight (filler words, unaddressed points, suggested follow-ups). This use case is chosen because:
- It has a clear start/end (meeting boundaries)
- Feedback value is immediately testable
- It constrains the system prompt design to one domain
- It maps directly to a 90-second demo

Other use cases (language practice, negotiation, learning) are **Phase 2+ only**.

### Non-Goals (V1)

- No always-on 24/7 listening -- sessions are user-initiated with explicit start/stop
- No multi-user support -- single user, single device
- No on-device LLM inference -- cloud-only reasoning
- No persistent memory across sessions -- each session is independent
- No App Store distribution -- TestFlight / personal device only
- No custom hardware -- AirPods + iPhone only

---

## 2. Architecture: Two Loops (Core Design)

The key architectural decision is to **decouple continuous listening from deep reasoning**. Instead of trying to answer every phrase in 300ms, the system operates in two independent cycles:

### Loop 1: Always-On Listener (real-time, lightweight)

Runs continuously on iPhone. Its only job is **capture and transcription**.

```
AirPods mic -> iPhone (Silero VAD on-device) -> Deepgram Nova-3 (streaming STT)
-> Transcript buffer with timestamps (local storage)
```

- No LLM calls in this loop
- Cost: ~$0.46/hour of active speech
- Aggressive VAD sends only real voice, reducing usage by 50-70%

### Loop 2: Deep Reasoning Engine (async, event-triggered)

Runs **periodically or by events**, not on every utterance. It processes accumulated transcript with a powerful reasoning model.

```
Transcript buffer (last N minutes)
-> Reasoning model (o4-mini / Gemini 2.5 Pro / Claude Sonnet)
-> Rich analysis (5-30s processing)
-> Cartesia Sonic-3 TTS -> Whisper to AirPods
```

**Triggers:**
- **Time**: every 5, 10, or 15 minutes of accumulated speech
- **Event**: user tap, silence > 30s, end of conversation segment
- **Context**: transcript mentions a preconfigured keyword or topic

### Connectivity and Offline Behavior

- **Loop 1 depends on cloud STT** (Deepgram). If connectivity drops, audio chunks are buffered locally and sent when reconnected. No real-time transcription is available offline.
- **Loop 2 is cloud-only.** If offline when a trigger fires, the trigger is deferred until connectivity returns.
- **Fallback**: If network is unavailable for >5 minutes during an active session, the app notifies the user with a subtle audio cue and continues buffering raw audio locally (capped at 50MB / ~25 min of audio).

### Hardware Constraints

- **AirPods Pro battery**: ~6 hours with active microphone. Hard cap on continuous session length.
- **iPhone battery**: Continuous Bluetooth audio streaming + network calls drains ~10-15%/hour. A full 6-hour session may consume 60-90% battery.
- **Implication**: Sessions default to a maximum of 2 hours with explicit user extension. The app warns at 80% AirPods battery.

### Diagram

```
┌─────────────────────────────────────────────────┐
│  LOOP 1: Always-On Listener (real-time)         │
│                                                 │
│  AirPods -> Phone (Silero VAD) -> Deepgram STT │
│  -> Rolling Transcript Buffer (local/cloud)     │
└──────────────────┬──────────────────────────────┘
                   │ trigger (timer / event / tap)
                   ▼
┌─────────────────────────────────────────────────┐
│  LOOP 2: Deep Reasoning (async, 5-30s)          │
│                                                 │
│  Transcript chunk -> o4-mini / Gemini 2.5 Pro   │
│  / Claude Sonnet -> Rich analysis               │
│  -> Cartesia TTS -> Whisper to AirPods          │
└─────────────────────────────────────────────────┘
```

---

## 3. Stack

| Layer | Component | Role |
|------|-----------|-----|
| **VAD** | Silero VAD | On-device voice detection, filters silence |
| **STT** | Deepgram Nova-3 | Streaming transcription, ~$0.0077/min |
| **LLM** | o4-mini / Gemini 2.5 Pro / Claude Sonnet | Async deep reasoning |
| **TTS** | Cartesia Sonic-3 | Natural real-time voice |
| **Framework** | Pipecat or LiveKit (optional) | Voice pipeline orchestration |
| **Backend** | Python FastAPI on Cloud Run | Hosts Loop 2 logic, receives transcript, calls LLM, returns TTS audio |
| **Storage** | Local (Core Data / SQLite) | Transcript buffer, session metadata. No cloud persistence in V1 |
| **Client** | Native iOS app (Swift) | AVAudioSession + Bluetooth/AirPods |

---

## 4. Estimated Costs

| Component | Usage pattern | 5h speech/month | 30h speech/month |
|------------|--------------|-------------|--------------|
| **STT** (Deepgram) | Continuous during speech | ~$2.30 | ~$14 |
| **LLM** (o4-mini) | Every 10 min -> ~30 calls/5h | ~$0.50-2 | ~$3-12 |
| **TTS** (Cartesia) | Short bursts | ~$1-3 | ~$5-15 |
| **Infra** (small VM) | Always on | ~$10-20 | ~$10-20 |
| **Total** | - | **~$15-27/month** | **~$32-61/month** |

**Cost levers:**
- Aggressive VAD reduces STT and LLM by 50-70%
- Free tiers: Deepgram ($200 credits), Cartesia (20k chars/month free)
- Use mini models where possible
- Local STT/TTS (faster-whisper + Kokoro) as future optimization

---

## 5. Use Cases and Prompt Design

The two-loop design enables **rich, contextual** feedback impossible in an instant-response system:

- **Meeting coaching** (V1 target): filler-word analysis, missed points, follow-up suggestions
- **Language practice** (V2): level assessment, grammar correction, improved sentence rewrites
- **Negotiation insights** (V2): stance-shift detection, tone analysis, leverage points
- **Learning summaries** (V2): synthesis of key points from classes or conferences, links to prior knowledge

### System Prompt Design (Loop 2)

The quality of whispered insights depends almost entirely on the system prompt. For V1 (meeting coaching), the prompt must:

1. **Role**: Act as a concise meeting coach. Output must be speakable in <15 seconds.
2. **Input format**: Timestamped transcript chunk with speaker labels (when diarization is available) or undifferentiated text (V1).
3. **Analysis instructions**: Count filler words, identify unanswered questions, detect action items, note tone shifts.
4. **Output format**: One to three bullet insights, prioritized by actionability. No preamble, no pleasantries.
5. **Constraints**: Never repeat information from a previous whisper. Never interrupt with trivial observations.

This prompt is a **living artifact** -- it must be iterated weekly based on the useful-whisper rate metric.

Example output (what the user hears):
> "You said 'basically' four times. Maria raised a budget concern you didn't address. Consider circling back before wrapping up."

---

## 6. Known Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| iOS background audio killed by OS | **Critical** | Validate in PoC (see `aiasis-poc.md`). Fallbacks: foreground-only, Android, companion hardware |
| Privacy / consent for ambient capture | **High** | Local-only storage, auto-delete after session, visible recording indicator, pause mechanism |
| Trigger timing (annoying vs useless) | **High** | Validate in PoC with distraction test before building pipeline |
| No speaker diarization in V1 | **Medium** | Accept undifferentiated text for V1. Add Deepgram diarization in Phase 2 |
| Battery drain exceeds acceptable threshold | **Medium** | Measure in PoC. Default 2h session cap. Warn at 80% AirPods battery |
| Competitive pressure (Limitless, Apple) | **Low (for prototype)** | V1 is personal use. Moat analysis needed before any public launch |

---

## 7. Privacy Specification

Decide from day one -- these shape the architecture and are much harder to retrofit.

- **Storage**: Local-only transcripts in V1. No cloud persistence of user speech.
- **Retention**: Auto-delete transcript buffer at session end. Configurable up to 24h max.
- **Encryption**: HTTPS for all API calls. Local storage in iOS encrypted container (Data Protection).
- **Indicator**: iOS status bar mic indicator active at all times during session.
- **Control**: Immediate pause/resume via tap. Session requires explicit start/stop.
- **Third parties**: Transcripts sent to Deepgram (STT) and LLM provider. No other data sharing.

### Security Baseline

- **Secrets**: No provider API keys in client bundle. Use short-lived signed tokens issued by backend.
- **Transport**: TLS only. Certificate pinning on mobile client if feasible.
- **Storage**: Transcript data encrypted at rest. Strict TTL auto-delete job.
- **Access**: Per-user data isolation. Server-side auth on every transcript read/write.
- **Audit**: Append-only audit log for access and deletion events.

---

## 8. Roadmap

| Phase | Duration | Deliverable |
|------|----------|-----------|
| **0. PoC** | 1 week | Validate product hypothesis and critical risks (see `aiasis-poc.md`) |
| **1. Loop 1 MVP** | 2-3 weeks | iOS app transcribes via AirPods in background and accumulates buffer |
| **2. Loop 2 MVP** | 1-2 weeks | Timer/tap trigger -> LLM call -> TTS playback |
| **3. Integration** | 1-2 weeks | Both loops running end-to-end, minimal UI |
| **4. Refinement** | Ongoing | Intelligent triggers, diarization, cross-session memory |

Phase 0 is a prerequisite. If the PoC fails, revisit architecture before proceeding.

### Phase 5: Public Launch (post-MVP)

**Track A -- Technical Publish:**
- Public repo: `README.md` with architecture and quickstart, `LICENSE`, `SECURITY.md`, `PRIVACY.md`
- Demo assets: 90-second screen + audio walkthrough, sequence diagram, measured latency and cost tables

**Track B -- Product Publish:**
- Landing page: problem ("You forget key moments from live conversations"), promise ("AI whispers high-value insights at the right moment"), differentiator ("Deep async reasoning, not shallow instant replies")
- Waitlist form with role/use-case capture (founder / sales / manager / student / language learner)
- Early access: explicit consent agreement, supported regions only, region-gate where ambient recording laws are stricter

**Launch KPIs (first 30 days):**
- Waitlist conversion from landing page >= 8%
- Demo completion rate >= 35%
- Insight usefulness self-rating >= 4/5
- Daily active pilot users >= 10

---

## 9. Release Gate

Before publishing an MVP or opening a waitlist, **every** item below must pass.

| # | Gate | Acceptance Criterion |
|---|------|---------------------|
| 1 | Background audio capture | 30+ min continuous on iOS without OS kill, tested 3 times |
| 2 | End-to-end latency | p95 trigger -> voice insight delivered < 12 seconds |
| 3 | Recording indicator | iOS status bar mic indicator visible at all times during session |
| 4 | Pause/resume | Tap-to-pause responds in < 500ms, confirmed via audio cue |
| 5 | Data retention | Transcripts auto-deleted after session end (or 24h max). Verified by inspecting local storage |
| 6 | Encryption | HTTPS for all API calls. Local transcript stored in iOS encrypted container (Data Protection) |
| 7 | Demo | One reproducible 90-second meeting coaching demo, screen-recorded |
| 8 | Battery | 1-hour session consumes < 20% iPhone battery |

If any gate fails, do not publish. Fix and retest.
