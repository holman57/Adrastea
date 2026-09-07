# Contributing to Adrastea

Thank you for your interest in contributing to the Adrastea architecture!

## Architectural Boundary Principles
When contributing, please respect the boundary between System Alpha and System Beta:
- **System Alpha (Deterministic)**: Must remain lightweight, fast, and free of heavy external dependencies or blocking calls.
- **System Beta (Probabilistic)**: Operates asynchronously, handling deep reasoning, MCP integration, and dynamic triage without hanging the deterministic execution loop.
- **IPC Protocol**: All signals between Alpha and Beta must follow the standardized control signal contract defined in the architecture specification.

## Development Workflow
1. Fork the repo and create a feature branch (`git checkout -b feat/your-feature`).
2. Run test suites: `python -m unittest discover tests`.
3. Adhere to PEP 8, typed dataclasses, and comprehensive docstrings.
4. Submit a PR describing your architectural changes.
