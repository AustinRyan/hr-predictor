# Phase 8 — LangGraph Explanation Agent (Optional)

## Required reading
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 8 section
3. `./abstract.md` — Phases 0–7 complete
4. `./src/models/overview.md` — SHAP contribution format
5. `./src/api/overview.md` — existing endpoint patterns

---

## Objective
Add a natural-language explanation layer. Given a prediction's SHAP contributions and matchup context, produce a 3-sentence "why this pick" narrative streamed to the UI via SSE.

**This phase is optional.** Skip if the product is working well without it. Use Claude Sonnet via Anthropic API.

**Scope boundary:** Explanation only. No new predictions. No model changes.

---

## Deliverables

### 1. Directory structure

```
src/agents/
├── __init__.py
├── overview.md
├── explainer.py           # LangGraph graph
├── prompts.py             # system prompts
├── schemas.py             # Pydantic models for agent I/O
└── cache.py               # Redis cache for explanations
```

### 2. Agent design (`src/agents/explainer.py`)

Use LangGraph. Even for a single LLM call, the graph abstraction makes it extensible.

Graph:
```
[build_context] → [generate_explanation] → [validate] → END
                                               ↓ (if invalid)
                                         [retry_once]
```

**Node: `build_context`**
Input: `MatchupExplanationInput` (game_pk, batter_id)
- Load prediction row from DB
- Load matchup_features for this game/batter/pitcher
- Load top-10 SHAP contributions (stored in `predictions.feature_contributions`)
- Build a structured context dict:
  ```python
  {
    "batter": {name, team, recent_form_narrative},
    "pitcher": {name, throws, pitch_arsenal_summary},
    "park": {name, hr_factor_handedness, elevation},
    "weather": {temp, wind_description, roof_status},
    "probability": {at_least_one, expected_hrs},
    "top_drivers": [  # top 3 positive and top 2 negative SHAP contributions
      {feature_name_human_readable, direction, magnitude}
    ]
  }
  ```
- Feature names translated to human-readable ("b_barrel_pct_30d" → "30-day barrel rate")

**Node: `generate_explanation`**
Uses Anthropic API (Claude Sonnet 4.6 — use claude-sonnet-4-6 model string). System prompt:

```
You are an MLB analyst writing concise prop-bet rationales. Given a matchup's features
and a model's top drivers, write exactly 3 sentences explaining why this batter is (or
isn't) likely to homer today.

Rules:
- Cite real numbers from the context, never invent.
- Lead with the strongest driver.
- Mention park and weather only if they are among the top drivers.
- No hedging words like "might" or "could". Be direct.
- No promotional language.

Return JSON: {"explanation": "...", "confidence": "high|medium|low"}
```

User message: JSON-dumped context.

**Node: `validate`**
- Check that explanation cites at least one number from the context
- Check length (3 sentences, ±1 tolerance)
- Check no banned phrases ("guaranteed", "lock", "sure thing")
- If fails, route to `retry_once`

**Node: `retry_once`**
Re-run `generate_explanation` with an appended message: "Your previous attempt failed validation: {reason}. Try again."

If retry also fails, return a template fallback: "Model predicts {prob}% HR probability. Top driver: {feature_name}."

### 3. Caching

`src/agents/cache.py`:
- Cache key: `explain:{prediction_id}:{model_version}`
- Value: the validated explanation JSON
- TTL: 24 hours (predictions are generated daily)
- On cache hit, skip entire graph

### 4. API endpoint

Add to `src/api/routers/matchup.py`:

#### `GET /matchup/{game_pk}/{batter_id}/explanation`
Streamed SSE response. Each event is a token. Final event is `{done: true, confidence: "..."}`.

Cache-aware: if cached, stream the full cached response in one event.

### 5. UI integration (in `ui/` — this can be a small addition to Phase 7 code)

On `/matchup/[gamePk]/[batterId]` page:
- New card: "Analyst View"
- On page load, fetch the SSE stream
- Show typing indicator while streaming
- Display the 3-sentence narrative
- If stream fails, hide the card silently (never show an error for an explainer — it's garnish, not critical)

### 6. Tests

- `tests/agents/test_explainer.py`:
  - Mock Anthropic client for unit tests (this is fine — the LLM isn't the data source here, it's a transformation)
  - Given a known context, validate the graph produces a 3-sentence output
  - Validator rejects an explanation missing numbers; retry node is invoked
  - Cache hit skips LLM call
- `tests/api/test_explanation_endpoint.py`:
  - SSE stream returns tokens
  - Cached response returns immediately

### 7. Configuration

Add to `.env.example`:
```
ANTHROPIC_API_KEY=
EXPLAINER_MODEL=claude-sonnet-4-6
EXPLAINER_ENABLED=true
```

If `EXPLAINER_ENABLED=false`, endpoint returns 404. Frontend hides the card.

### 8. Phase docs

- `phases/phase8/ACCEPTANCE.md`
- `phases/phase8/NOTES.md`
- `src/agents/overview.md`

---

## Acceptance checklist

```markdown
# Phase 8 — Acceptance Checklist

## Agent functionality
- [ ] `uv run python -m agents.explainer --game-pk {X} --batter-id {Y}` produces a 3-sentence explanation
- [ ] Explanation cites at least one number from the matchup context
- [ ] No hallucinations: every number in the explanation appears in the context dict
- [ ] Length: 3 sentences (±1 tolerance)
- [ ] Banned phrases absent

## API
- [ ] `GET /matchup/{game_pk}/{batter_id}/explanation` streams via SSE
- [ ] Response time (cold, uncached): < 5 seconds
- [ ] Response time (cached): < 100ms
- [ ] Invalid IDs return 404
- [ ] With `EXPLAINER_ENABLED=false`, endpoint returns 404 cleanly

## Validation & fallback
- [ ] When LLM output is invalid, retry is triggered
- [ ] When retry also fails, template fallback is returned (not an error to the user)

## UI
- [ ] /matchup page displays streamed explanation with typing effect
- [ ] If SSE fails, page continues to render fully; card is hidden silently
- [ ] Explanation reads naturally on mobile and desktop

## Tests
- [ ] `uv run pytest tests/agents -v` all pass
- [ ] `uv run pytest tests/api/test_explanation_endpoint.py -v` passes

## Docs
- [ ] `src/agents/overview.md` documents the graph, validation rules, prompts
- [ ] `abstract.md` shows Phase 8 complete (or skipped with note)
```

---

## Non-negotiables

- **No hallucinated numbers.** Validator enforces this; but also the prompt is explicit.
- **Explanations are garnish, not load-bearing.** If the agent fails, the page still works.
- **Cache aggressively.** 24-hour TTL. Don't re-run LLMs on the same prediction.
- **API key never logged.** Redact in all log output.
- **Budget control.** Cost per explanation should be < $0.01; at ~150 predictions/day that's ~$1.50/day max. Log token usage.

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Manually verify three different matchups produce distinct, context-appropriate explanations
3. Verify cache behavior
4. Walk acceptance checklist
5. Update docs
6. Commit + tag `phase-8-complete`

---

## STOP condition (and project conclusion)

This is the final planned phase. After Phase 8:
- Full `MASTER_PLAN.md` is complete
- `abstract.md` reflects a shipped v1
- Future iterations (odds integration, CLV tracking, live in-game updates) get their own `phases/phaseN/` with a fresh prompt

Report:
1. Sample explanations for 3 different matchups
2. Token cost per explanation
3. Cache hit rate after a day of use
4. Any final polish items worth flagging for a future iteration
