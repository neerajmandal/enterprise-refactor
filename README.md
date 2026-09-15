# enterprise-refactor

CLI that prompts for a **legacy repo**, **target repo**, and **Cursor env**, then runs one of three Cursor Cloud Agent workflows. Both repos are always cloned into that env.

On start it draws a green **REFACTOR** home screen with the connected env, model, and repos, then an arrow-key menu: **↑↓** to move between Analyze, Plan, Implement, Runs, and Settings, **enter** to run, **q** to quit. Change the model with `--model` or `CURSOR_MODEL` in `.env`. **Settings** can override repos and the API key for the current process only; it does not write `.env`. **Runs** shows the last agent IDs and branch names from `.refactor/state.json`.

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
| **Plan** | Asks for a modernization prompt (`--prompt` / `CURSOR_PLAN_PROMPT`), then lists remote heads on the **legacy** repo (`git ls-remote`, then `gh`). The picker puts `refactor/analyze-*` first and defaults to the newest of those. The cloud agent fetches and checks out that remote branch before reading current-state docs, then writes a phased plan on `refactor/plan-<date>` on the **target** repo and opens a PR there. Or pass `--analyze-branch`. |
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
| **Settings** (menu) | session | Override repos and API key until you quit; never writes `.env` |
| `--analyze-branch` | picker / state | Legacy branch Plan reads (skips the picker) |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

`CURSOR_REPO` is still accepted as an alias for the legacy source.

Exit codes: `0` finished, `1` never started (auth/config/network or missing prior workflow), `2` run started then failed.
