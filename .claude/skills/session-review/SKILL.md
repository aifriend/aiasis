# Session Review Skill

## Trigger

Use when the user asks to: review sessions, evaluate the PoC, check ratings, compare prompt versions, calculate metrics, prepare Day 7 evaluation.

## STUB — Refine after real session data exists (Day 5+)

### Session Log Format

Each session file is `logs/session-YYYY-MM-DD-HHMMSS.jsonl` containing JSON lines:

```json
{"type": "whisper", "timestamp": "...", "trigger_type": "manual|timer", "transcript_chunk_length": 1234, "llm_response": "...", "tts_duration_ms": 4500, "user_rating": 4, "aborted": false, "prompt_version": "v1"}
{"type": "whisper", "timestamp": "...", "trigger_type": "timer", "transcript_chunk_length": 2000, "llm_response": "...", "tts_duration_ms": 0, "user_rating": null, "aborted": true, "prompt_version": "v1"}
{"type": "summary", "session_start": "...", "session_end": "...", "total_whispers": 5, "avg_rating": 3.8, "abort_count": 1, "duration_minutes": 25, "prompt_version": "v1"}
```

### Metrics to Calculate (from docs/aiasis-poc.md)

| Metric | Target | How to Calculate |
|--------|--------|------------------|
| Useful-whisper rate | ≥ 60% | Whispers rated ≥ 3 / total rated whispers |
| Incremental insight | ≥ 40% | Whispers rated ≥ 4 / total rated whispers |
| Distraction score | ≤ 2/10 | From manual user assessment (not in logs) |
| Abort rate | ≤ 20% | Aborted whispers / total whispers |
| Latency (trigger→audio) | < 15s | tts_duration_ms proxy + LLM time |
| Session willingness | ≥ 3 sessions | Count of session files |

### Analysis Commands (to be implemented)

```bash
# Parse all session files and print metrics table
python -c "
import json, glob, statistics
files = sorted(glob.glob('logs/session-*.jsonl'))
for f in files:
    whispers = []
    with open(f) as fh:
        for line in fh:
            data = json.loads(line)
            if data.get('type') == 'whisper':
                whispers.append(data)
    rated = [w for w in whispers if w.get('user_rating') is not None]
    if not rated:
        print(f'{f}: no rated whispers')
        continue
    avg = statistics.mean(w['user_rating'] for w in rated)
    useful = sum(1 for w in rated if w['user_rating'] >= 3) / len(rated) * 100
    aborted = sum(1 for w in whispers if w.get('aborted')) / len(whispers) * 100
    print(f'{f}: {len(whispers)} whispers, avg rating {avg:.1f}, useful {useful:.0f}%, abort {aborted:.0f}%')
"
```

### Compare Prompt Versions

Group sessions by `prompt_version` and compare average ratings across versions.

### Identify Weakest Whispers

Sort whispers by `user_rating` ascending. Show the `llm_response` and `transcript_chunk_length` for the lowest-rated ones to guide prompt iteration.
