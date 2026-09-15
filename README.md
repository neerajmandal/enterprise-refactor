# enterprise-refactor

CLI that prompts for a **legacy repo**, **target repo**, and **Cursor env**, then runs one of three Cursor Cloud Agent workflows. Both repos are always cloned into that env.

On start it draws a green **REFACTOR AGENT** splash, then an arrow-key menu: **↑↓** to move between Analyze, Plan, and Implement, **enter** to run. Change the model with `--model` or `CURSOR_MODEL` in `.env`.

## Setup

```bash
uv sync
```

No flags or env vars are required to start. On first run the CLI prompts for anything missing (`CURSOR_API_KEY`, `CURSOR_LEGACY_REPO`, `CURSOR_MODERN_REPO`, `CURSOR_ENV`) and writes them to `.env`. Later runs load `.env` and show **CLI ready**.

Create a key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations).

## Usage

```bash
uv run enterprise-refactor
uv run enterprise-refactor analyze
uv run enterprise-refactor plan
uv run enterprise-refactor implement
```

| Workflow | What it does |
| --- | --- |
| **Analyze** | Discovery-only map of the legacy system (target repo is context). Pushes `refactor/analyze-<date>` on the **legacy** repo with `docs/modernization/CURRENT_STATE_ANALYSIS.md` and `docs/modernization/current-state.md`. |
| **Plan** | Needs Analyze. Asks for a modernization prompt (`--prompt` / `CURSOR_PLAN_PROMPT`), then uses current-state docs to write a phased plan with subtasks on `refactor/plan-<date>` on the **target** repo (`plan.md`, `phases/`, `plan.json`) and opens a PR there. |
| **Implement** | Needs Analyze and Plan. Unattended: implement each undone phase, check it off, test, then next. After the last phase, uses computer use to record a walkthrough (`docs/refactor/walkthrough.mp4`). |

Agent IDs and branch names are stored in gitignored `.refactor/state.json`.

Optional flags still override `.env`:

| Flag / env | Default | Purpose |
| --- | --- | --- |
| `--legacy-repo` / `CURSOR_LEGACY_REPO` | prompted / `.env` | Legacy source git URL |
| `--modern-repo` / `CURSOR_MODERN_REPO` | prompted / `.env` | Modern target git URL |
| `--cursor-env` / `CURSOR_ENV` | prompted / `.env` | Cursor cloud environment name |
| `--legacy-ref` / `CURSOR_LEGACY_REF` | `main` | Legacy starting branch or SHA |
| `--modern-ref` / `CURSOR_MODERN_REF` | `main` | Modern starting branch or SHA |
| `--model` / `CURSOR_MODEL` | `composer-2.5` | Model id |
| `--prompt` / `CURSOR_PLAN_PROMPT` | prompted | Plan-only modernization ask (not written to `.env`) |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

`CURSOR_REPO` is still accepted as an alias for the legacy source.

Exit codes: `0` finished, `1` never started (auth/config/network or missing prior workflow), `2` run started then failed.
