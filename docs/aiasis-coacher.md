# AIASIS Meeting Coach — Design Doc

## The Core Tension

You're in a meeting. You're talking, listening, thinking, reacting. Cognitive load is already high. Any coaching intervention that adds load instead of removing it **hurts more than it helps**.

The fundamental design question isn't "what insight can I generate?" — it's **"what's the minimum information that changes behavior in the next 30 seconds?"**

## Insight Tiers

Not all coaching has the same urgency or delivery window. Three tiers:

### Tier 1: Tactical (next 10 seconds)
- **Unanswered questions** — someone asked something and it got buried
- **Uncommitted actions** — "we should" without "I will by Friday"
- **Name recall** — "the person who just spoke is from the finance team" (requires speaker ID)

### Tier 2: Strategic (next 2-5 minutes)
- **Agenda drift** — you've been on this topic 15 minutes, you had 3 more to cover
- **Power dynamics** — one person has talked 70% of the time, others are silent
- **Missing stakeholder input** — "design hasn't weighed in yet"

### Tier 3: Meta (post-meeting value)
- **Commitment tracker** — running list of who promised what
- **Sentiment shift** — energy dropped after topic X
- **Your own patterns** — "you've said 'um' 40 times" or "you haven't asked a single question"

## The Interruption Budget

The user has a finite tolerance for being whispered to. Every whisper that lands builds trust. Every one that doesn't erodes it. After 3-4 bad whispers in a row, the user mentally tunes out or turns it off.

This means the system doesn't just need good advice — it needs **restraint**. The cost of a false positive (useless whisper) is higher than the cost of a false negative (missed insight). Silence is always a safe default.

Practical implications:
- **Fewer, better whispers** beat frequent mediocre ones
- The system should actively choose *not* to speak when it has nothing high-value
- The "no observation" escape hatch is not a failure mode — it's the system working correctly
- A session with 3 whispers rated 5/5 is better than 10 whispers averaging 3/5

---

# Part 1: Validate Now (PoC)

Everything below is testable with the current two-loop architecture, a single undifferentiated transcript stream, and no speaker diarization. Uses the `meeting-coach` preset and `prompts/v1.txt`.

## What The PoC Can Test

The fundamental product question: **does a human actually act on whispered coaching during a live meeting?**

If the answer is no — if any audio interruption during a meeting is fundamentally unwelcome — then the real product might be the post-meeting debrief, not real-time coaching. That's the hypothesis we need to kill or confirm in 3+ sessions.

Secondary questions:
- Does the *timing* of delivery matter more than the *content*?
- Does self-selected (manual) triggering outperform automatic triggering?
- Is there a sweet spot for whisper frequency, or is any frequency annoying?

## Trigger Models We Can Test Now

### 1. Timer Trigger (current — "Shoulder Tap")
Timer goes off → coach analyzes buffer → speaks one line. Simple. The timing is random relative to the conversation's rhythm, but it's the baseline.

**Test question**: Do timer-triggered whispers ever land at a useful moment by chance? What's the hit rate?

**Config**: `trigger_interval_min` in dashboard Session tab (default: 10 min for meeting-coach preset).

### 2. Manual Trigger (current — spacebar)
User decides when they want coaching. This is the control group: when a human picks the moment, does the advice land better?

**Test question**: Do manually-triggered whispers consistently rate higher than timer-triggered ones?

### 3. Prepared Whisper (buildable now)
Coach generates an insight on the timer but **holds it** until VAD detects silence > 3 seconds (a natural pause in conversation). The insight is ready; delivery waits for the right moment.

**Test question**: Does pause-aligned delivery feel less intrusive than random-timer delivery?

**Implementation**: Loop 2 generates the coaching text but doesn't immediately send to TTS. Instead, it stores the text and sets a `pending_whisper` flag. Loop 1's VAD monitors for sustained silence (configurable threshold, e.g. 3 seconds of no speech). When silence threshold is met, the stored text is sent to TTS. If no pause arrives within a `whisper_expiry` window (e.g. 60 seconds), either deliver anyway or discard — configurable via dashboard.

**New config fields needed**: `prepared_whisper_enabled` (bool), `silence_threshold_sec` (float, default 3.0), `whisper_expiry_sec` (int, default 60).

### 4. Confidence Gating (prompt-level, buildable now)
Add to the system prompt: "Rate your confidence 1-10 that this insight will change the user's behavior in the next 30 seconds. If below 7, output nothing."

**Test question**: Does a confidence gate reduce interruption fatigue without killing useful whispers?

**Implementation**: Pure prompt engineering. The LLM self-gates. If it outputs the "no observation" token, TTS is skipped. No code changes beyond the prompt.

**Risk**: LLMs are poorly calibrated self-raters. The gate may be too aggressive (always silent) or too permissive (never gates). Test with threshold values of 5, 7, and 9 to find the sweet spot.

### 5. Diminishing Frequency (buildable now)
First whisper at 5 min, second at 10, third at 20. If the user manually triggers (spacebar), reset the curve — they're hungry for input.

**Test question**: Does exponential backoff match the natural decay of useful observations in a meeting?

**Implementation**: Timer interval increases after each auto-trigger. Manual trigger resets the counter. Simple state in main.py.

**Rationale**: Meetings frontload new information. The first 10 minutes have the most novel content. By minute 40, the conversation is likely in territory the LLM has already analyzed. Backoff matches this natural information curve.

### Recommended Test Order

Test these sequentially, not simultaneously. Each needs 3+ sessions to produce signal:

1. **Baseline**: Timer trigger only (current). 3 sessions.
2. **Manual vs timer**: Compare ratings. If manual consistently wins, timing > content.
3. **Confidence gating**: Add to timer trigger. Does it reduce noise without killing signal?
4. **Prepared whisper**: The highest-effort change. Only build if confidence gating alone doesn't solve interruption fatigue.
5. **Diminishing frequency**: Can layer on top of whichever delivery model wins.

## Insight Types Testable Now

Without speaker diarization, the transcript is one undifferentiated stream. That limits Tier 1 (we can't know *who* asked a question or *who* is being silent). But we can still test:

- **Conversation looping** — repeated keywords/topics across the buffer. The LLM can detect "this is the third time pricing came up" from raw transcript alone.
- **Vague commitments** — phrases like "we should," "maybe next week," "someone needs to." Detectable without knowing who said them.
- **Agenda drift** — if the user provides an agenda in the prompt (or pastes it before the meeting starts), the LLM can compare transcript topics against it.
- **Long monologues** — if the buffer is dominated by continuous speech with no turn-taking, flag it. (Crude proxy for power dynamics without speaker ID.)
- **Strategic observations** — general meeting-flow guidance. This is what the v1 prompt already does (Tier 2).
- **Dead air / stalled discussion** — sustained silence or circular phrasing that suggests the group is stuck.

### What We Can't Test Yet (requires speaker ID)

- Who asked a question vs. who answered it
- Whether *you* specifically are over-talking or under-contributing
- Whether a specific person has been silent for the whole meeting
- Whether *you* made the vague commitment or someone else did

This limitation means the PoC coach must frame observations about the *conversation*, not about *individuals*. "Someone made a vague commitment" not "you said something vague."

## What To Measure

Each session log already captures whisper ratings (1-5). Across 3+ sessions, look for:

1. **Average rating by trigger type** — timer vs manual vs prepared-whisper. Which delivery method produces the highest-rated whispers?
2. **Rating distribution** — are most whispers 3s (meh) or is it bimodal (1s and 5s)? Bimodal means the coach is sometimes brilliant and sometimes useless — that's a gating problem, not a quality problem.
3. **Abort rate** — how often does the user hit `x` to stop TTS? High abort = bad timing or bad content. Track both separately if possible (subjective log note).
4. **Whisper-to-action gap** — subjective: after a session, did any whisper actually change what you did in the meeting? Even one "yes" in 3 sessions is a strong signal.
5. **Fatigue curve** — do ratings decline over the session? If whisper #1 is a 4 and whisper #8 is a 2, the system is wearing out its welcome.
6. **Silence ratio** — what fraction of trigger events produced "no observation"? Too high (>80%) means the coach is over-gated. Too low (<20%) means it's not filtering enough.

### Post-Session Debrief Protocol

After each test session, write a 3-line subjective note in the log:
1. Did any whisper change what I did or said? Which one?
2. Was the coach more annoying or more helpful overall?
3. One thing I wish it had said but didn't.

This qualitative data is more valuable than rating averages at the PoC stage.

## Go/No-Go After PoC Validation

**Go** if:
- At least 30% of whispers rate 4+
- At least one whisper per session demonstrably changed behavior
- User doesn't turn it off mid-session out of frustration
- Prepared-whisper or confidence-gating measurably outperforms raw timer

**No-go** if:
- Most whispers are ignored or aborted
- The user prefers manual-only triggering (meaning auto-coaching isn't wanted)
- Ratings are flat 2-3 across sessions (the advice is technically correct but useless in context)

**Pivot options if no-go on real-time**:
- **Debrief-only mode** (Silent Scorecard) — accumulate observations silently, deliver a 60-second spoken summary when the meeting ends
- **On-demand only** — remove auto-trigger entirely, coach only speaks when asked (spacebar). This is still a useful product if the advice is good.
- **Written-only** — coach outputs to a text log visible on screen, no audio. Lower interruption cost, but requires looking at your laptop.

---

# Part 2: Post-PoC Vision

Everything below assumes real-time meeting coaching has been validated. These ideas require capabilities beyond the current PoC (speaker diarization, multi-agent orchestration, persistent learning).

## Capabilities Needed

| Capability | Unlocks | Effort |
|---|---|---|
| Speaker diarization | Tier 1 triggers, per-person analytics | Medium (Deepgram supports it) |
| Meeting memory | "Last week you committed to X" | Medium (persistent store + RAG) |
| Calendar integration | Agenda-aware coaching, auto-detect meeting end | Low |
| Multi-agent orchestration | Parallel tier analysis, blackboard arbitration | High |
| Rating-based learning | Suppress low-value categories over time | Low (log analysis + prompt injection) |

## Trigger Scenarios That Require Future Capabilities

**Right after someone asks you a direct question**
The transcript shows a question directed at you. You have 2-3 seconds before silence gets awkward. The coach whispers: *"They asked this same thing last week — you committed to X."*
Requires: speaker diarization + intent classification + memory of prior meetings.

**When you're about to commit to something vague**
You just said "yeah we can probably do that by next sprint." The coach whispers: *"Pin it down — who, what, when."*
Requires: speaker ID (to know *you* said it, not someone else).

**When a decision is being made without you noticing**
Someone says "so we're going with option B then" and nobody pushes back. The coach whispers: *"Decision happening — do you agree with B?"*
Requires: consensus-detection patterns + speaker-aware turn analysis.

**Silence after conflict**
Someone pushed back on your idea. There's a pause. The coach whispers: *"Acknowledge their concern, then restate your point differently."*
Requires: sentiment analysis + speaker ID + conflict detection.

## Interaction Modes To Explore

### The "Question Anticipator" Model
Instead of reacting to what happened, predict what's coming. If the transcript shows someone building toward an objection, whisper the counter-argument before they finish. High-risk, high-reward — when it works, you look brilliant.

### The "Silent Scorecard" Model
No voice during the meeting. The coach accumulates insights and delivers a 60-second debrief when the meeting ends (detected via "goodbye" patterns or calendar integration). Zero cognitive load, but loses real-time value.

### The "Two-Speed" Model
Coach runs silently, accumulating observations. It has an **urgency threshold** — if it detects something critical (a commitment, an unanswered question, a decision being made), it breaks silence and whispers. Everything else goes to the post-meeting debrief. This is the most promising model because it naturally solves the interruption budget problem: silence is the default, interruption is the exception.

## Multi-Agent Blackboard Architecture

Stop treating Tier 1, Tier 2, and Tier 3 as sections of one prompt. Treat them as **parallel specialist agents**.

- **Tier 1 agent**: immediate tactical interventions
- **Tier 2 agent**: strategic meeting-flow guidance
- **Tier 3 agent**: reflective and longitudinal observations

This separation matters because these are different cognitive jobs with different time horizons, different interruption permissions, and different expiration windows.

### Why The Split Makes Sense

A single prompt is forced to answer three questions at once:

- What matters right now?
- What matters in the next few minutes?
- What matters only as a debrief or longer-term pattern?

That creates internal conflict. A monolithic coach blends tactical, strategic, and reflective feedback into one output stream, even though those forms of coaching don't deserve the same delivery channel.

### The Blackboard As Attention Governor

The blackboard is not passive storage. It is the **attention governor** of the system. Its job is to continuously decide:

- Is there anything worth saying at all?
- What is the single highest-value recommendation?
- Should it be spoken now, held for pause, saved for debrief, or suppressed?
- Has this recommendation expired?
- Is it novel, or is it repeating something already said?

The hard part is not generating recommendations. The hard part is deciding what deserves airtime.

### Structured Candidates, Not Prose

Each tier agent contributes a **structured candidate**, not freeform text:

```
{
  "source_tier": 1,
  "recommendation": "Unanswered question about timeline — address it now",
  "urgency": 9,
  "confidence": 8,
  "novelty": true,
  "shelf_life_sec": 15,
  "evidence": "...can we get a timeline on that? [no response, topic changed]",
  "delivery": "speak_now"
}
```

Fields:
- **source_tier** — which specialist produced this
- **recommendation** — the coaching text to speak
- **urgency** (1-10) — how time-sensitive
- **confidence** (1-10) — how sure the agent is this will change behavior
- **novelty** — is this new information or a repeat?
- **shelf_life_sec** — seconds before this expires and should be discarded
- **evidence** — transcript excerpt supporting the recommendation
- **delivery** — `speak_now` / `hold_for_pause` / `save_for_debrief` / `suppress`

This lets the blackboard compare like with like instead of reinterpreting ambiguous prose from other LLMs.

### Time Decay And Unequal Privilege

The tiers don't compete equally for live audio time:

- **Tier 1** has the strongest permission to interrupt. Decays in seconds.
- **Tier 2** usually waits for a pause. Decays in minutes.
- **Tier 3** defaults to debrief. Remains useful until session end.

Without explicit time decay, the system risks delivering advice that is correct but socially late.

### The Biggest Risk: Building A Committee

This architecture becomes dangerous if it turns into a committee of LLMs speaking in vague prose.

Failure mode:
- Three agents produce soft natural-language recommendations
- A fourth agent tries to interpret and combine them
- Latency rises, duplicate advice appears, the system becomes hard to reason about

Safest principle:
- Specialist analyzers can be expressive
- The blackboard should remain as explicit and rule-bound as possible

The freer the blackboard is, the less trustworthy the system becomes. Prefer deterministic rules (highest urgency wins, tier 1 always preempts tier 3, expired candidates are dropped) over another LLM call to "pick the best one."

### The Right Mental Model

- Tier agents answer: **What do I notice?**
- Blackboard answers: **What matters now?**
- Delivery layer answers: **Should I speak yet?**

Three different problems. Should not be collapsed into one model call.

### Rating-Based Prompt Evolution

Over multiple sessions, patterns emerge in the JSONL logs. If the user consistently rates commitment-tracking insights as 5/5 but filler-word observations as 1/5, the system should learn to suppress low-value categories and amplify high-value ones.

Implementation path:
1. **Manual** (now): Review logs, manually adjust prompt emphasis
2. **Semi-auto** (next): Script that aggregates ratings by insight category and suggests prompt edits
3. **Auto** (future): System appends "Focus on: [high-rated categories]. Avoid: [low-rated categories]" to the prompt, derived from aggregate log analysis

This is one of the cheapest high-value improvements — it turns the rating system from a measurement tool into a feedback loop.

---

## Product-Level Thesis

**Many specialists compete for one scarce resource: the user's attention.**

That is why the blackboard idea is compelling. It changes the system from a recommendation generator into an **attention allocation system**.

The meeting coach's deepest value isn't telling you what to say — it's making you aware of what you're not noticing. The quiet person, the drifting agenda, the commitment nobody wrote down, the question that got steamrolled. Your attention is finite. The coach extends it.

And for this product, that is probably the right frame.
