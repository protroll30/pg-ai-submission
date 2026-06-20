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

### v1.2: Acoustic Tuning & Resilience Hardening

**Status:** Complete

**What was built:**

- **Acoustic tuning:** Widened `stopSpeakingPlan` wait seconds to **0.8s** and back-off seconds to **1.0s** to counter false barge-in triggers caused by the target bot's synthetic latency (simulated typing/processing pauses that standard VAD engines misread as user speech)
- **Dynamic override framework:** Extended `run_evals.py` with granular per-scenario `api_overrides`, including per-case Cartesia Sonic 3.5 voice hot-swapping for multilingual (`es`) and accented English (`en`) test cases
- **Resilience logic:** Shifted scheduling-task `persona_modifier` instructions to a **compliance-first** mode when the target state machine is rigid, and integrated a **self-recovery** intent in the Vapi system prompt so the patient simulator resets the conversation if the target agent enters an incoherent loop

**Observation:** Early runs exposed transcript collisions during high-latency target API responses — the patient simulator was barging in on artificial processing delays, not real user turns. Tuning endpointing/back-off thresholds eliminated most overlap. Multilingual cases (especially Spanglish code-switching) required dynamic TTS model swaps rather than a single default voice. Scheduling scenarios also needed explicit recovery behavior; without it, target-side agentic collapse caused premature hangups and wasted call time.

**Impact:**

- **Collision rate:** Transcript overlap during high-latency responses was largely eliminated
- **Localization:** Conversational context held through Spanglish code-switching via per-case phonetic model selection
- **Reliability:** Graceful handling of target-side agentic collapse reduced total call termination rates by an estimated **30%**

**Decision:** Keep per-scenario `api_overrides` as the primary tuning surface for acoustic and voice settings, and treat compliance-first persona rules plus self-recovery prompting as default resilience patterns for baseline scheduling tests going forward.
