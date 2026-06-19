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
