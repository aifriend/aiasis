# AIASIS - Proof of Concept

> Prove the whisper is worth hearing before engineering how it reaches the ear.

This document defines a lightweight PoC to validate the aiasis product hypothesis **before** committing to the full blueprint (`aiasis-blueprint.md`). The PoC answers three questions:

1. **Is whispered coaching during a conversation actually useful?**
2. **Can a person listen to two audio streams (conversation + whisper) without losing focus?**
3. **Does the system prompt produce actionable insights from raw transcripts?**

If any answer is "no", the blueprint needs revision before implementation begins.

---

## Philosophy

The blueprint front-loads hard engineering (iOS background audio, Cloud Run backend, Deepgram streaming). But the biggest risk isn't technical -- it's **product risk**: maybe whispered coaching is distracting, maybe the LLM insights are generic, maybe the cadence feels wrong.

The PoC validates the product first, with the minimum possible engineering.

---

## Approach: Mac-First, Zero Infrastructure

Instead of starting with native iOS, start with a **Python script on a Mac laptop**:

- Mac has no background audio restrictions. `sounddevice` captures mic audio trivially.
- You sit in meetings with your laptop anyway.
- AirPods connected to Mac work identically for playback.
- The entire Loop 1 + Loop 2 pipeline fits in a single Python script.
- No backend, no Cloud Run, no FastAPI, no Pipecat, no LiveKit.

This gets a working end-to-end prototype in **3-4 days** instead of 14.

### Simplified Stack (PoC only)

| Layer | PoC Component | Why |
|------|--------------|-----|
| **Audio capture** | `sounddevice` (Python) | Zero config, works on Mac immediately |
| **VAD** | Silero VAD (Python) | Same as blueprint, already validated |
| **STT** | Deepgram Nova-3 (websocket) | Same as blueprint, Python SDK available |
| **LLM** | Direct API call (`requests`) | No backend needed. Call OpenAI/Anthropic directly from the script |
| **TTS** | `edge-tts` (Python) | Free, high-quality Microsoft neural voices. pip-installable. Much better than macOS `say` -- closer to production quality, won't bias distraction tests with robotic voice |
| **Client** | Terminal + AirPods connected to Mac | No app needed |

**What's eliminated vs the blueprint:**
- No iOS app
- No Swift
- No AVAudioSession complexity
- No Cloud Run / FastAPI backend
- No Pipecat / LiveKit
- No Cartesia API (`edge-tts` as free stand-in)
- No Core Data / SQLite (just in-memory buffer)

### Audio Device Setup (Mac)

When AirPods connect to Mac, the default input device may not switch automatically. Before running the script:

1. Run `python -m sounddevice` to list available audio devices
2. Identify the AirPods device index for both input (mic) and output (playback)
3. Set explicitly in the script: `sd.default.device = [input_idx, output_idx]`
4. Verify with a 5-second test recording before starting any session

If AirPods mic quality is poor over Bluetooth (SCO codec limitation), fall back to Mac built-in mic for capture and use AirPods for output only. This is acceptable for PoC -- the real product captures from AirPods on iOS where AAC codec is available.

---

## Pre-Code Validation (Days 1-2)

Before writing the Python script, run two manual tests that require zero code:

### Test 1: Wizard of Oz (Day 1, morning)

Validate that LLM coaching insights are useful on real meeting transcripts.

**Steps:**
1. Get a meeting transcript. Options (fastest first):
   - Use an existing Zoom/Meet recording with auto-generated transcript
   - Record yourself in a conversation using Voice Memos, transcribe via Deepgram playground
   - Use a public meeting recording (e.g. a YouTube panel discussion) as test material
2. Take a 10-minute chunk of the transcript.
3. Paste it into ChatGPT or Claude with the meeting coaching system prompt (see blueprint section 5).
4. Read the output. Ask: "Would I have wanted to hear this mid-meeting?"
5. Repeat with 3 different transcript chunks from different conversations.
6. **Save the LLM outputs** -- they become the test material for Test 2.

**Pass criteria:** At least 2 out of 3 outputs contain at least one insight you'd consider actionable.

**If it fails:** The system prompt needs work. Iterate the prompt before building anything. If after 5 prompt iterations the output is still generic or useless, reconsider whether meeting coaching is the right V1 use case.

### Test 1b: Control Baseline (Day 1, afternoon)

Measure whether the coaching adds value beyond what you'd notice on your own.

**Steps:**
1. Take one of the transcript chunks from Test 1 that you have NOT yet analyzed.
2. Read through it yourself. Write down anything you'd flag as a coaching insight.
3. Now run it through the LLM prompt.
4. Compare: did the LLM catch things you missed? Did it surface anything non-obvious?

**Pass criteria:** The LLM output contains at least 1 insight you did not write down yourself.

**If it fails:** The coaching is not additive. Either the prompt is too shallow or the use case doesn't benefit from AI assistance. Iterate the prompt to focus on patterns humans miss (filler word counts, unanswered questions over time, tone shifts).

### Test 2: Distraction Test (Day 2)

Validate that a person can process whispered coaching while holding a conversation. **Uses the real LLM outputs from Test 1** -- not generic pre-written phrases.

**Steps:**
1. Take the saved LLM outputs from Test 1. Convert them to audio using `edge-tts` (or macOS `say` as fallback).
2. Put on AirPods.
3. **Volume calibration first**: Play one coaching phrase at different volumes while listening to music or a podcast. Find the level where the whisper is clearly audible but doesn't overpower the primary audio. Note the volume setting.
4. Have a real conversation with someone (or join a video call, minimum 20 minutes).
5. Every 8-10 minutes, manually play one coaching audio clip at the calibrated volume.
6. After the conversation, rate each interruption:
   - Could you understand the whisper? (yes/no)
   - Did you lose track of the conversation? (yes/no)
   - Was the timing acceptable? (yes/no)
   - Did you feel the need to stop it mid-playback? (yes/no)

**Pass criteria:** At least 3 out of 5 interruptions are understandable without losing the conversation.

**If it fails:** Whispered coaching during live conversation may be fundamentally broken UX. Consider alternative delivery:
- **Silence-gap only**: Whisper only when no one has spoken for >5 seconds
- **Visual**: Text notification on Apple Watch instead of audio
- **Post-session**: Deliver coaching summary after the meeting ends, not during

---

## PoC Build (Days 3-5)

If both manual tests pass, build the minimal end-to-end pipeline.

### Day 3: Loop 1 (capture + transcribe)

Build a Python script that:
1. Captures audio from Mac microphone (AirPods mic if connected) using `sounddevice`
   - On transient overload, drop audio frames safely (no crash, no exception flood) and continue session
2. Runs Silero VAD to detect speech segments
3. Streams speech segments to Deepgram Nova-3 via websocket
4. Accumulates transcribed text in a rolling in-memory buffer with timestamps

**Deliverable:** Run the script, talk for 5 minutes, see accurate transcript printed to terminal.

### Day 4: Loop 2 (reason + speak)

Extend the script to:
1. Every 10 minutes (or on keyboard press), send only new transcript since the last whisper (+ short context tail)
2. Send it to an LLM (OpenAI or Anthropic API) with the meeting coaching prompt
3. Take the LLM response, synthesize to one deep actionable whisper (hard word cap), and speak it aloud via `edge-tts` + `mpv`/`afplay`
4. Audio routes through AirPods if they're the active output device
5. **Abort key** (`x`): kills TTS playback immediately if the whisper lands at a bad moment

**Deliverable:** Talk for 10 minutes, press a key, hear a coaching whisper through AirPods within 15 seconds. Press `x` to confirm abort works.

### Day 5: Integration + First Real Test

1. Add automatic timer trigger (every 10 minutes of accumulated speech)
2. Add session start/stop (keyboard: `s` to start, `q` to quit)
   - If Deepgram connection fails at startup, do not crash; stay in CLI and allow `s` retry
3. Add simple logging: timestamp each whisper, log the prompt input and LLM output
   - Default mode: lightweight logs (no verbose payload snapshots)
   - Debug mode (`--debug-logs`): include event markers for `space`-trigger pause/resume and coaching voice playback start/end
   - Debug mode (`--debug-logs`): if no new transcript exists since the previous whisper, log skip event
   - Debug mode (`--debug-logs`): log exact transcript text sent to LLM and exact spoken coaching text for each whisper
4. Add 1-5 rating prompt after each whisper (keyboard: press 1-5 immediately after hearing the whisper)
5. **Test in a real meeting or simulated conversation for 30+ minutes** (minimum 20 min for valid data)
6. Store prompt version alongside ratings (`prompts/v1.txt`, `prompts/v2.txt`, etc.)

**Deliverable:** Session log with per-whisper ratings and prompt version in normal mode, plus debug-only fields/events when `--debug-logs` is enabled:
- Debug events: `manual_trigger_pressed`
- Debug events: `transcription_paused` / `transcription_resumed`
- Debug events: `coaching_voice_started` / `coaching_voice_finished`
- Debug events: `whisper_skipped_no_new_transcript`
- Debug per-whisper payload fields: `transcript_sent_to_llm`, `spoken_text`

### Day 6: More Sessions + Prompt Iteration

1. Run session #2 in a different context (e.g. if session #1 was video call, try in-person or solo work)
2. Review Day 5 ratings. Identify the weakest whisper. Adjust the prompt. Save as new version.
3. Run session #3 with the updated prompt.
4. Minimum: **3 sessions across at least 2 different contexts** before evaluation.

**Deliverable:** 3 session logs with ratings, at least 2 prompt versions tested.

---

## PoC Evaluation (Day 7)

### Metrics to Collect

| Metric | Target | How |
|--------|--------|-----|
| Useful-whisper rate | >= 50% (PoC bar is lower than MVP) | Average of 1-5 ratings across all sessions. >= 3.0 average passes |
| Conversation disruption | <= 1 lost-focus moment per 30 min | Self-report after each session |
| Abort rate | < 30% of whispers aborted | Count `x` key presses vs total whispers |
| End-to-end latency (trigger -> audio) | < 15s (PoC bar is looser than MVP) | Log timestamps |
| Incremental value | At least 1 non-obvious insight per session | Compare against control baseline (Test 1b) |
| Prompt iteration count | Track versions and score trend | Version the prompt file, compare ratings across versions |

### Decision Matrix

| Result | Action |
|--------|--------|
| Whispers useful + not disruptive | **Go.** Proceed to blueprint Phase 1 (iOS app). |
| Whispers useful BUT disruptive | **Pivot delivery.** Try visual-only (Apple Watch text), or whisper only during silence gaps. Re-test. |
| Whispers NOT useful + not disruptive | **Pivot prompt.** Spend 3 more days iterating the system prompt. If still not useful after 5 versions, reconsider the use case (try language practice instead). |
| Whispers NOT useful AND disruptive | **Stop.** The core hypothesis is invalid. Revisit the entire product concept before investing more time. |

---

## Alternative V1 Use Case: Language Practice

If meeting coaching fails at the PoC stage, **language practice** is the backup use case. It has one key advantage for a solo builder: **you can test it anytime, anywhere, by yourself.**

- Talk to yourself in a target language for 10 minutes
- Get feedback on grammar, vocabulary, level assessment
- Repeat 5 times in a single day
- Iterate the prompt 5 times in a single day

The feedback loop is 100x faster than meeting coaching (which requires actual meetings).

The PoC script needs minimal changes: swap the system prompt and remove the multi-speaker assumptions.

---

## What the PoC Does NOT Validate

These items remain open risks for the full blueprint and must be addressed in Phase 1:

- **iOS background audio** -- the PoC runs on Mac. iOS constraints are untested.
- **Bluetooth audio routing on iOS** -- AirPods on Mac just work. iOS requires AVAudioSession configuration.
- **Battery consumption** -- Mac is plugged in. iPhone/AirPods battery drain is unknown.
- **Privacy architecture** -- the PoC runs locally with no persistence. Production needs encryption, retention, consent.
- **Speaker diarization** -- the PoC uses undifferentiated text.

These are engineering risks. The PoC validates the **product** risk first.

---

## Summary

```
Day 1:     Wizard of Oz + Control Baseline               -> Insight quality validated
Day 2:     Distraction Test (with real LLM outputs)       -> Dual-listen UX validated
Days 3-4:  Python script on Mac (capture + reason + speak) -> Working end-to-end prototype
Day 5:     First real test session + ratings               -> Initial data
Day 6:     Two more sessions + prompt iteration            -> Sufficient data
Day 7:     Evaluation + go/pivot/stop decision             -> Decision made
```

Total: **7 days, zero infrastructure, ~$0 cost** (free tiers cover everything).

If the PoC succeeds, proceed to the blueprint with confidence that you're building something worth the iOS pain. If it fails, you've lost one week, not eight.

---

## Follow-Up Experiments (Post-PoC, Pre-MVP)

If the PoC passes, run these low-cost experiments during blueprint Phase 1 to refine the product before the full build:

1. **Trigger A/B test**: Compare (A) fixed timer every 10 minutes vs (B) silence-end detection + confidence threshold. Measure useful-whisper rate for each. Run on the Mac PoC script -- no iOS needed.
2. **Insight quality rating**: After each whisper, prompt yourself to rate 1-5. Log the ratings alongside the prompt version. Track whether prompt iterations improve the score.
3. **Regret metric**: After each session, review the whisper log and mark which interruptions were unnecessary. Target: zero "I wish it hadn't said that" moments per session.
4. **Dynamic trigger interval**: Modify the PoC script to shorten the trigger interval during high-intensity conversation (many speaker turns) and lengthen it during low-intensity stretches. Compare against fixed interval.
5. **Topic segmentation before LLM**: Pre-process the transcript buffer to extract topic boundaries before sending to the LLM. Test whether this reduces prompt noise and improves insight specificity.
