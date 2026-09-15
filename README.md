# enterprise-refactor

CLI that makes **one** Cursor Cloud Agent call via `Agent.prompt()` and prints the result.

On start it draws a green **REFACTOR AGENT** splash: Cursor env on top pointing at both repos, with the model as a single line below. Change the model with `--model` or `CURSOR_MODEL` in `.env`.

## Setup

```bash
uv sync
```

No flags or env vars are required to start. On first run the CLI prompts for anything missing (`CURSOR_API_KEY`, `CURSOR_LEGACY_REPO`, `CURSOR_MODERN_REPO`) and writes them to `.env`. Later runs load `.env` and show **CLI ready**.

Create a key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations).

## Usage

```bash
uv run enterprise-refactor
uv run enterprise-refactor "Map the legacy checkout flow onto the modern repo"
```

Optional flags still override `.env`:

| Flag / env | Default | Purpose |
| --- | --- | --- |
| `--legacy-repo` / `CURSOR_LEGACY_REPO` | prompted / `.env` | Legacy source git URL |
| `--modern-repo` / `CURSOR_MODERN_REPO` | prompted / `.env` | Modern target git URL |
| `--cursor-env` / `CURSOR_ENV` | `Cursor Cloud` | Connected Cursor environment label |
| `--legacy-ref` / `CURSOR_LEGACY_REF` | `main` | Legacy starting branch or SHA |
| `--modern-ref` / `CURSOR_MODERN_REF` | `main` | Modern starting branch or SHA |
| `--model` / `CURSOR_MODEL` | `composer-2.5` | Model id |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

`CURSOR_REPO` is still accepted as an alias for the legacy source.

Exit codes: `0` finished, `1` never started (auth/config/network), `2` run started then failed.
