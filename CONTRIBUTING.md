# Contributing

Thanks for your interest in contributing! This project welcomes issues, ideas, and pull requests.

## Quick Start (Dev)

- Python: 3.8+
- Node.js: 18+ (for the `frontend`)

Setup backend:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env  # then add OPENAI_API_KEY
python verify_setup.py
```

Setup frontend:

```bash
cd frontend
npm install
npm run dev
```

Alternatively, use Docker: `./start.sh`.

## Branch & PR Workflow

- Create a feature branch from `main`: `git checkout -b feat/<short-name>`
- Keep changes focused and small; add/update docs as needed
- Run local checks and manual smoke tests
- Open a PR with a clear description and motivation

## Coding Guidelines

- Python style: follow PEP 8; prefer type hints where practical
- Keep functions small and well-documented; add docstrings for public APIs
- Avoid committing secrets, large binaries, and generated files
- Update `README.md` when user flows or setup change

## Commit Messages

Use clear, imperative messages. Optionally follow Conventional Commits, e.g.:
`feat: add realtime generator reconnect logic`

## Reporting Issues

Include steps to reproduce, expected vs actual behavior, logs (sanitized), and environment info.

