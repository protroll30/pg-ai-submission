# Voice-Bot Testing Framework
This project is an automated testing pipeline for voice AI agents, focused on evaluating conversational latency, turn-taking, and persona adherence.

## Tech Stack
- **Language**: Python 3.12
- **Frameworks**: FastAPI, Twilio SDK, OpenAI Realtime API
- **Tooling**: Cursor (IDE), Claude Code (Agentic CLI)

## Core Engineering Principles
- **Latency Obsession**: Every interaction must target sub-500ms round-trip latency. If performance degrades, investigate buffering, network overhead, or STT/TTS overhead immediately.
- **Adaptive Architecture**: Prioritize the most efficient path to high-quality conversational flow. If current infrastructure (e.g., custom WebSocket handlers) hits a performance bottleneck, evaluate an orchestration-layer switch (e.g., Vapi/Retell) before proceeding.
- **Goal-Driven Execution**: Every task must have a verifiable success criterion. If a requirement is ambiguous, stop and ask.
- **Iterative Transparency**: If a major technical decision (like an infrastructure pivot) is made, update the iteration log in `@README.md` immediately. The repository should always reflect the current "best" solution.

## Workflow Rules
- **Verification**: Always run verification after implementation. If no test script exists for the component being modified, write a simple one.
- **Human-in-the-Loop**: Use Claude Code for autonomous scaffolding and multi-file changes; use Cursor’s Composer/Chat for deep-dive debugging and quality assurance.
- **Constraint**: Never commit secrets or API keys. Always use `.env` files and verify against `@.gitignore`.

## Commands
- **Run Server**: `uvicorn main:app --reload`
- **Run Tests**: `pytest tests/`

## Known Technical Guardrails
- **Audio Buffers**: Streaming raw binary audio requires precise chunking. If latency spikes, check buffer size and jitter settings in `main.py`.
- **Interruption ("Barge-in")**: Conversational fluidity depends heavily on system prompt brevity and low-latency audio transmission.