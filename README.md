# enterprise-refactor

A terminal app that modernizes a legacy codebase into a new one, one step at a time, using [Cursor Cloud Agents](https://cursor.com/agents).

You give it two git repositories:

- **Source** — the legacy system you are leaving behind
- **Target** — the modern repository you are building

Each step starts a cloud agent in a named Cursor environment with **both** repos checked out. The agent pushes its work to a dated `refactor/…` branch. You stay in the terminal: pick a step, watch the run, then come back to the menu.

```bash
uv sync
uv run enterprise-refactor
```

Create an API key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations). A diagram of the three workflows is in [docs/architecture.md](docs/architecture.md).

## What the three steps do

Run them in order. Each one reads what the previous step wrote.

| Step | You are asking | Where the result goes |
| --- | --- | --- |
| **Analyze** | “How does the legacy system work today?” | A discovery write-up on the **source** repo. No pull request. |
| **Plan** | “Turn that picture into a phased modernization plan.” | A plan on the **target** repo, plus a pull request. |
| **Implement** | “Build the phases I choose, and test them.” | Code and tests on the **target** repo. The last phase records a UI walkthrough. |

### Analyze

Discovery only. The target repo is there for context; the agent does not change it.

It pushes `refactor/analyze-YYYYMMDD-HHMMSS` on the **source** repo with:

- `docs/modernization/CURRENT_STATE_ANALYSIS.md`
- `docs/modernization/current-state.md`

### Plan

You pick which source branch to read (usually the newest analyze branch) and type what you want modernized. The agent checks out that branch, then writes a phased plan on the **target** repo and opens a pull request there.

The branch is `refactor/plan-YYYYMMDD-HHMMSS`, with:

- `docs/refactor/plan.md` — the plan in prose
- `docs/refactor/plan.json` — the same plan as data the Implement step reads
- `docs/refactor/phases/NN-<slug>.md` — one file per phase

Every plan ends with a **computer-use** phase that exercises the UI. Earlier phases name a `test_command` and list the UI flows that last phase should cover.

### Implement

You pick a target **plan** or **implement** branch, then choose which phases to build. The agent codes each selected phase, checks it off, and runs that phase’s unit test (`test_command`).

Computer-use UI testing runs only as the **last** plan phase, and only after every unit test has passed. That pass adds `docs/refactor/walkthrough.mp4` and a pull request.

Work lands on `refactor/implement-YYYYMMDD-HHMMSS` on the target repo.

## Using the menu

```bash
uv run enterprise-refactor
```

The home screen is a full-screen menu. **↑↓** or **j/k** move, **1–5** jump, **enter** selects, **q** quits. When a workflow finishes you return to the menu, with the highlight on the next typical step.

| Item | What it does |
| --- | --- |
| **Analyze** | Starts the discovery run described above. |
| **Plan** | Asks which source branch to read, then asks for the modernization prompt. |
| **Implement** | Asks which target branch and which phases to build. |
| **Runs** | Shows the last agent IDs and branch names from `.refactor/state.json`. Read-only. **Enter** or **q** returns. |
| **Settings** | Override the source repo, target repo, or API key for this session only. This updates the process environment and **does not write `.env`**. The environment name and model stay as they were at startup (change those with flags or `.env`). |

Skip the menu and run one step directly:

```bash
uv run enterprise-refactor analyze
uv run enterprise-refactor plan
uv run enterprise-refactor implement
```

A terminal is required for prompts and the menu. To run without a terminal, pass `analyze`, `plan`, or `implement` and supply any missing values with flags or `.env`.

## First launch

1. If a `.env` file exists, it is loaded. A variable already set in the environment wins over `.env`.
2. The CLI looks for connection settings in flags, then the environment:
   - `CURSOR_API_KEY`
   - `CURSOR_LEGACY_REPO` (or `CURSOR_REPO`)
   - `CURSOR_MODERN_REPO`
   - `CURSOR_ENV`
3. Anything still missing is asked for on a waiting home screen. A repo can be a git URL or `owner/repo`. The API key is hidden as you type. Answers are saved to `.env`, along with defaults for refs and model if those keys are new.
4. The home screen redraws with the environment, model, source repo, and target repo, then runs the step you named or opens the menu.

## Choosing a branch and phases

### Plan

If you do not pass `--analyze-branch`, the CLI lists remote branches on the source repo (`git ls-remote` and `gh`, merged when both work). Analyze branches (`refactor/analyze-*`) sort first, newest date stamp first. The default is the newest analyze branch, then the last branch saved in state, then `--legacy-ref` / `main`.

**↑↓** and **enter** choose. **Esc** or Back cancels and does not start an agent. If the remote list fails, you are asked to type a branch name. Without a terminal, Plan uses `--analyze-branch` or the branch already in `.refactor/state.json`.

The modernization prompt comes **after** the branch (`--prompt`, `CURSOR_PLAN_PROMPT`, or a typed prompt). It is not saved to `.env`.

### Implement

If you do not pass `--plan-branch`, the CLI lists remote branches on the **target** repo. Implement branches sort first, then plan branches, then everything else (newest date stamp first within each group). The default is the newest implement branch, then the newest plan branch, then the last branch in state, then `--modern-ref` / `main`.

**↑↓** and **enter** choose. **Esc** or Back cancels.

The CLI then reads `docs/refactor/plan.json` from that branch and shows the phases:

- Finished phases are checked and locked.
- Pending phases start unchecked. **Space** toggles one.
- **Implement all remaining** (`a`) runs every phase that is not done: unit tests first, UI last.
- **Implement selected** runs the phases you toggled, plus any unfinished phases they depend on. The UI computer-use pass runs only when your selection includes the last phase and every unit test has passed.
- **Esc** or Back returns to the branch list.

The last plan phase is always computer-use. Older `plan.json` files that omit it still show a virtual `99-computer-use` phase.

If `plan.json` cannot be read, you can still choose **Implement all remaining**. The agent then implements every undone phase on the branch.

Without a terminal, Implement uses `--plan-branch` or the branch in `.refactor/state.json`. Pass `--phases 01-foo,03-bar` to name phase ids. Omit `--phases` to implement everything remaining.

## What happens during a run

The CLI starts a Cursor Cloud Agent (`cursor-sdk`) with:

- the model from `--model` / `CURSOR_MODEL` (default `composer-2.5`)
- the named cloud environment from `CURSOR_ENV`
- both repos (`owner/repo` is expanded to `https://github.com/owner/repo.git`)
- a starting ref for each repo: Analyze uses `--legacy-ref` and `--modern-ref` (default `main`); Plan starts the source side on the analyze branch you picked; Implement starts the target side on the plan or implement branch you picked

While the agent works, the CLI streams its thinking, tool calls, tasks, status, usage, and reply, then waits until the cloud run finishes or fails. Agent IDs that look like `bc-…` are printed as `https://cursor.com/agents/<id>`.

Run IDs and branch names are stored in `.refactor/state.json` (gitignored). Secrets stay in `.env`.

## Flags and environment

| Flag / env | Default | Purpose |
| --- | --- | --- |
| `--legacy-repo` / `CURSOR_LEGACY_REPO` | prompted / `.env` | Source git URL or `owner/repo` |
| `--modern-repo` / `CURSOR_MODERN_REPO` | prompted / `.env` | Target git URL or `owner/repo` |
| `--cursor-env` / `CURSOR_ENV` | prompted / `.env` | Cursor cloud environment name |
| `--legacy-ref` / `CURSOR_LEGACY_REF` | `main` | Source starting branch or SHA (Analyze) |
| `--modern-ref` / `CURSOR_MODERN_REF` | `main` | Target starting branch or SHA |
| `--model` / `CURSOR_MODEL` | `composer-2.5` | Model id |
| `--prompt` / `CURSOR_PLAN_PROMPT` | prompted | Plan modernization ask (not saved to `.env`) |
| `--analyze-branch` | picker / state | Source branch Plan reads (skips the picker) |
| `--plan-branch` | picker / state | Target plan or implement branch Implement reads (skips the branch picker) |
| `--phases` | all remaining | Comma-separated `plan.json` ids (skips the phase picker) |
| `CURSOR_API_KEY` | prompted / `.env` | User or service-account API key |

`CURSOR_REPO` is accepted as an alias for the source repo.

## Exit codes

These apply when you pass `analyze`, `plan`, or `implement` on the command line:

| Code | Meaning |
| --- | --- |
| `0` | The workflow finished |
| `1` | It never started (auth, config, network, or Implement without a saved Analyze/Plan branch) |
| `2` | The cloud run started, then failed |

Quitting the home menu, or backing out of the Plan branch picker, exits `0`.
