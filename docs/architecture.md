# Architecture

High-level view of how the CLI drives Analyze, Plan, and Implement on Cursor Cloud Agents.

## System context

The local CLI never edits the two application repos itself. It collects settings, picks a branch and phases, then starts a cloud agent that already has both git checkouts.

```mermaid
flowchart LR
    operator[Operator] --> cli[enterprise-refactor CLI]
    cli --> envFile[".env"]
    cli --> stateFile[".refactor/state.json"]
    cli --> cursorAPI[Cursor Cloud Agent API]
    cursorAPI --> cloudEnv[Named cloud environment]
    cloudEnv --> legacyRepo[Legacy source repo]
    cloudEnv --> modernRepo[Modern target repo]
    cli --> gitRemote[git ls-remote / gh]
    gitRemote --> legacyRepo
    gitRemote --> modernRepo
```

## CLI packages

```mermaid
flowchart TB
    cli[cli.py] --> config[config]
    cli --> ui[ui screens and pickers]
    cli --> workflows[workflows]
    workflows --> cursor[integrations/cursor]
    workflows --> planDocs[plan document and selection]
    workflows --> state[state]
    ui --> git[integrations/git]
    ui --> planDocs
    cursor --> sdk[cursor-sdk]
    git --> remotes[GitHub remotes]
```

| Package | Role |
| --- | --- |
| `cli` | Flags, home menu, dispatch to a workflow |
| `config` | Resolve API key, repos, env, and model from flags / `.env` / prompts |
| `ui` | TUI home, runs, settings, and input |
| `pickers` | Analyze-branch, implement-branch, and phase lists |
| `workflows` | Analyze, Plan, and Implement prompts plus result handling |
| `integrations/cursor` | Session, stream, poll, and extract cloud-run results |
| `integrations/git` | List remotes and read `plan.json` from a branch |
| `plan` | Parse phase flags and plan documents |
| `state` | Last agent IDs and branch names |

## Workflows

Each workflow starts a cloud agent with both repositories. Artifacts land on a dated `refactor/*` branch.

```mermaid
flowchart TB
    start[CLI start] --> resolve[Resolve config]
    resolve --> menu{Menu or named workflow}
    menu --> analyze[Analyze]
    menu --> plan[Plan]
    menu --> implement[Implement]
    menu --> runs[Runs]
    menu --> settings[Settings]

    analyze --> analyzeAgent[Cloud agent on both repos]
    analyzeAgent --> analyzeOut["Legacy: refactor/analyze-YYYYMMDD<br/>docs/modernization/*"]

    plan --> pickAnalyze[Pick legacy analyze branch]
    pickAnalyze --> planAgent[Cloud agent]
    planAgent --> planOut["Target: refactor/plan-YYYYMMDD<br/>docs/refactor/plan.md + plan.json + phases<br/>PR on target"]

    implement --> pickPlan[Pick target plan or implement branch]
    pickPlan --> pickPhases[Pick pending phases]
    pickPhases --> implAgent[Cloud agent]
    implAgent --> implOut["Target: refactor/implement-YYYYMMDD<br/>code + unit tests<br/>last phase: computer-use walkthrough"]
```

Analyze writes discovery docs on the **legacy** repo and does not open a PR. Plan and Implement write on the **target** repo; Plan opens a PR. Implement runs `test_command` per selected unit-test phase and runs computer-use UI checks only as the last plan phase.
