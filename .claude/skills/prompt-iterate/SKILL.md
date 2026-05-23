# Prompt Iterate Skill

## Trigger

Use when the user asks to: improve the prompt, iterate on coaching quality, fix whisper quality, create a new prompt version.

## STUB — Refine after real session data exists (Day 5+)

### Workflow

1. **Load current prompt** from `prompts/v{latest}.txt`
2. **Load session data** — find lowest-rated whispers using session-review skill
3. **Identify patterns** in low-rated whispers:
   - Too generic? ("You should speak more clearly") → Add specificity rules
   - Too obvious? ("The meeting is going well") → Already forbidden in v1, but check
   - Bad timing? (Repeated something already said) → Check previous_whispers context
   - Too long? (> 15s spoken) → Tighten word count constraint
   - Not actionable? → Strengthen "actionable-first" priority
4. **Draft new prompt version** with targeted fixes
5. **Save as `prompts/vN.txt`** (increment version number)
6. **Test** by running a session with `--prompt prompts/vN.txt`
7. **Compare** ratings between old and new version using session-review skill

### Naming Convention

```
prompts/v1.txt  ← original
prompts/v2.txt  ← first iteration
prompts/v3.txt  ← second iteration
```

Auto-detect latest: `glob('prompts/v*.txt')`, sort by version number, pick highest.

### Prompt Quality Checklist

Before saving a new version, verify:
- [ ] Output rules: max ~40 words, speakable in <15s
- [ ] No greetings or preamble allowed
- [ ] "No notable observations" escape hatch present
- [ ] `previous_whispers` context awareness documented
- [ ] Actionability-first priority ordering
- [ ] Examples included (concrete, not abstract)

### What NOT to Change

- Don't add roles like "You are a helpful assistant" — keep it direct
- Don't add pleasantries or hedging language
- Don't remove the word count constraint
- Don't add multi-turn conversation — each call is stateless except for previous_whispers
