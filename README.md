# enterprise-refactor

Interactive CLI that drives three Cursor Cloud Agent workflows: **Analyze**, **Plan**, and **Implement**. Each run starts a cloud agent in a named Cursor environment with **both** git repos checked out (legacy source and modern target).

High-level diagrams: [docs/architecture.md](docs/architecture.md).

```bash
uv sync
uv run enterprise-refactor
```

Create an API key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations).

## How the CLI starts

1. Load `.env` if it exists (`os.environ.setdefault`, so a real env var wins).
2. Resolve connection settings from flags, then env / `.env`:
   - `CURSOR_API_KEY`
   - `CURSOR_LEGACY_REPO` (or `CURSOR_REPO`)
   - `CURSOR_MODERN_REPO`
   - `CURSOR_ENV`
3. If anything required is missing, draw the **REFACTOR** home screen in “waiting” mode and prompt for it. Valid repo values are a git URL or `owner/repo`. The API key is entered with a hidden prompt. Answers are written to `.env` (plus defaults for refs and model if those keys are new).
4. Draw the home screen again with Environment, Model, Source repo, and Target repo, then either run a named workflow or open the menu.

A TTY is required for prompts and the menu. Non-interactive use must pass `analyze`, `plan`, or `implement` and supply any missing values via flags or `.env`.

## Home menu

```bash
uv run enterprise-refactor
```

Full-screen TUI. **↑↓** or **j/k** move, **1–5** jump, **enter** selects, **q** quits. After a workflow finishes you return to the menu (highlight moves to the next typical step).

| Item | What happens |
| --- | --- |
| **Analyze** | Discovery-only map of the legacy system. Target repo is context only. Cloud agent pushes `refactor/analyze-YYYYMMDD` on the **legacy** repo (no PR) with `docs/modernization/CURRENT_STATE_ANALYSIS.md` and `docs/modernization/current-state.md`. |
| **Plan** | Pick which **legacy** remote branch to read, then enter a modernization prompt. Agent checks out that branch, writes a phased plan on `refactor/plan-YYYYMMDD` on the **target** repo (`docs/refactor/plan.md`, `docs/refactor/plan.json`, `docs/refactor/phases/NN-<slug>.md`), and opens a PR on the target only. Every plan ends with a default **computer-use** UI phase. Earlier phases list `test_command` plus `computer_use` flows for that last UI pass. |
| **Implement** | Pick a target **plan** or **implement** branch, then choose phases. Each implement phase is coded, checked off, and unit-tested (`test_command`). Computer-use UI testing runs only as the last plan phase, after every unit test has passed (`docs/refactor/walkthrough.mp4` + PR). |
| **Runs** | Read-only last agent IDs and branch names from `.refactor/state.json`. Enter or **q** returns. |
| **Settings** | Session-only override of legacy repo, modern repo, or API key. Updates process env; **does not write `.env`**. Env name and model stay as started (use flags / `.env`). |

Skip the menu:

```bash
uv run enterprise-refactor analyze
uv run enterprise-refactor plan
uv run enterprise-refactor implement
```

## Plan branch picker

Unless you pass `--analyze-branch`:

1. List remote heads on the legacy repo (`git ls-remote --heads` and `gh api` if available; names are merged).
2. Sort `refactor/analyze-*` first (newest date stamp first), then other branches.
3. Default selection is the newest analyze branch, else last used from state, else `--legacy-ref` / `main`.
4. **↑↓** / enter to choose, **esc** / Back to cancel (no agent).

If remotes cannot be listed, the CLI asks for a branch name. Non-TTY Plan uses `--analyze-branch` or the branch already in `.refactor/state.json`.

The modernization ask comes **after** the branch is chosen (`--prompt`, `CURSOR_PLAN_PROMPT`, or a prompt). That value is not written to `.env`.

## Implement branch and phase pickers

Unless you pass `--plan-branch`:

1. List remote heads on the **target** repo.
2. Sort `refactor/implement-*` first (newest date stamp first), then `refactor/plan-*`, then other branches.
3. Default selection is the newest implement branch, else the newest plan branch, else last used from state, else `--modern-ref` / `main`.
4. **↑↓** / enter to choose, **esc** / Back to cancel (no agent).

Then the CLI fetches `docs/refactor/plan.json` from that branch (`gh api`, then a shallow `git fetch` if needed) and draws the phase list:

- Done phases are checked and locked.
- Pending phases start unchecked. **space** toggles a pending phase.
- **Implement all remaining** (`a`) runs every phase that is not `done`: unit tests first, last-phase UI last.
- **Implement selected** runs the toggled pending phases and any undone dependencies. UI computer-use runs only if that selection includes the last phase and all unit tests passed.
- **esc** / Back returns to the branch list.

The last plan phase is always computer-use. Existing `plan.json` files that omit it still get a virtual `99-computer-use` phase in the picker.

If `plan.json` cannot be read, you can still choose **Implement all remaining** and the agent implements every undone phase on the branch.

Non-TTY Implement uses `--plan-branch` or the branch already in `.refactor/state.json`. Pass `--phases 01-foo,03-bar` to name phase ids; omit `--phases` to implement all remaining.

## What a cloud run does

The CLI creates a Cursor Cloud Agent (`cursor-sdk`) with:

- the selected `--model` / `CURSOR_MODEL` (default `composer-2.5`)
- `CURSOR_ENV` as the named cloud environment
- both repos as `CloudRepository` entries (`owner/repo` is expanded to `https://github.com/owner/repo.git`)
- starting refs: Analyze uses `--legacy-ref` / `--modern-ref` (default `main`); Plan starts the legacy side on the chosen analyze branch; Implement starts the target side on the chosen plan or implement branch

While the agent works, the CLI streams thinking, tools, tasks, status, usage, and assistant text, then polls until the cloud run finishes (or fails). Agent IDs print as `https://cursor.com/agents/<id>` when they look like `bc-…`.

Workflow IDs and branch names are stored in gitignored `.refactor/state.json`. Secrets stay in `.env`.

## Flags and env

| Flag / env | Default | Purpose |
| --- | --- | --- |
| `--legacy-repo` / `CURSOR_LEGACY_REPO` | prompted / `.env` | Legacy source git URL or `owner/repo` |
| `--modern-repo` / `CURSOR_MODERN_REPO` | prompted / `.env` | Modern target git URL or `owner/repo` |
| `--cursor-env` / `CURSOR_ENV` | prompted / `.env` | Cursor cloud environment name |
| `--legacy-ref` / `CURSOR_LEGACY_REF` | `main` | Legacy starting branch or SHA (Analyze) |
| `--modern-ref` / `CURSOR_MODERN_REF` | `main` | Target starting branch or SHA |
| `--model` / `CURSOR_MODEL` | `composer-2.5` | Model id |
| `--prompt` / `CURSOR_PLAN_PROMPT` | prompted | Plan modernization ask (not saved to `.env`) |
| `--analyze-branch` | picker / state | Legacy branch Plan reads (skips the picker) |
| `--plan-branch` | picker / state | Target plan or implement branch Implement reads (skips the branch picker) |
| `--phases` | all remaining | Comma-separated `plan.json` ids (skips the phase picker) |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

`CURSOR_REPO` is accepted as an alias for the legacy source.

## Exit codes

Used when you pass `analyze`, `plan`, or `implement` on the command line:

| Code | Meaning |
| --- | --- |
| `0` | Workflow finished |
| `1` | Never started (auth/config/network, or Implement without saved Analyze/Plan branches) |
| `2` | Cloud run started, then failed |

Quitting the home menu, or backing out of the Plan branch picker, exits `0`.
