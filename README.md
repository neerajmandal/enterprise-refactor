# enterprise-refactor

CLI that makes **one** Cursor Cloud Agent call via `Agent.prompt()` and prints the result.

## Setup

```bash
uv sync
```

No flags or env vars are required to start. On first run the CLI prompts for anything missing (`CURSOR_API_KEY`, `CURSOR_REPO`) and writes them to `.env`. Later runs load `.env` and print `CLI ready`.

Create a key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations).

## Usage

```bash
uv run enterprise-refactor
uv run enterprise-refactor "Summarize this repository"
```

Optional flags still override `.env`:

| Flag / env | Default | Purpose |
| --- | --- | --- |
| `--repo` / `CURSOR_REPO` | prompted / `.env` | Git URL cloned into the cloud VM |
| `--ref` / `CURSOR_REPO_REF` | `main` | Starting branch or SHA |
| `--model` / `CURSOR_MODEL` | `composer-2.5` | Model id |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

Exit codes: `0` finished, `1` never started (auth/config/network), `2` run started then failed.
