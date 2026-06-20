# pg-ai-submission
Automated voice-bot framework for stress-testing real-time conversational agents with low-latency LLM integration.

## Iteration Log

### v1.0: Raw Telephony Baseline (Inbound WebSockets)

**Status:** Complete

**What was built:** A minimal FastAPI server using raw Twilio WebSockets to handle low-level media streams, with two endpoints:

- `POST /voice` returns TwiML that connects an inbound Twilio call to a WebSocket stream
- `WS /media-stream` accepts the raw audio stream from Twilio and logs incoming packets

**Observation:** The Twilio-to-WebSocket routing works. Raw audio packets come through cleanly. But once I looked at the actual requirements, two problems stood out.

1. The bot needs to **initiate an outbound call** to a specific test line (`+1-805-439-8008`), not sit around waiting for someone to call in.
2. The biggest grading priority is **natural conversational voice** and **sensible turn-taking**. I benchmarked Vapi as a reference point. Even with concurrent audio streaming, it sits around ~850ms mouth-to-ear. A hand-rolled Python script doing STT, LLM, and TTS one step at a time would be much worse. Rough math: ~200ms transcription, ~300ms for the model, ~250ms for voice generation. Those add up sequentially instead of overlapping, and you still have blocking Python overhead on top. A raw WebSocket approach would realistically land at **1,500 to 2,000ms+**, which is nowhere near the sub-500ms target and would make turn-taking feel broken.

**Decision:** Drop the raw WebSocket path. Pivot to Vapi for v1.1 to handle outbound dialing and real-time audio orchestration.

### v1.1: Vapi Outbound Eval Runner (Patient Simulator)

**Status:** Complete

**What was built:**

- `run_evals.py` triggers outbound Vapi calls to the clinic test line (`+1-805-439-8008`) with 15 tiered persona scenarios across 6 categories (baseline, acoustic stress, state machine breakers, guardrail exploits, telephony edge cases, multilingual)
- CLI case selection (`python run_evals.py tc_05_frantic_interrupter`) so tests run individually, not as a batch
- Per-test `firstMessage` openers and `persona_modifier` injection via `assistantOverrides.variableValues` (wired to `{{test_name}}` and `{{persona_modifier}}` in the Vapi dashboard system prompt)
- `api_overrides` support for per-call Vapi tuning (e.g. `stopSpeakingPlan` on `tc_05_frantic_interrupter`)
- `main.py` repurposed as a Vapi webhook receiver (`POST /vapi-webhook`) that saves end-of-call transcripts to `transcripts/`

**Observation:** Vapi handles outbound dialing, STT, LLM routing, and TTS so the eval harness can focus on persona design and clinic-bot behavior rather than audio infrastructure. Separating `firstMessage` (what the patient says aloud) from `persona_modifier` (hidden behavior instructions) produces more realistic test calls than dumping raw test metadata into the opening line.

**Decision:** Use `run_evals.py` as the test trigger layer and `main.py` as the post-call capture layer. Evaluation is manual: trigger a case, review the saved transcript (and Vapi dashboard recording) against the scenario's expected behavior.
