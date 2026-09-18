# Workflows

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
    analyzeAgent --> analyzeOut["Legacy: refactor/analyze-YYYYMMDD-HHMMSS<br/>docs/modernization/*"]

    plan --> pickAnalyze[Pick legacy analyze branch]
    pickAnalyze --> planAgent[Cloud agent]
    planAgent --> planOut["Target: refactor/plan-YYYYMMDD-HHMMSS<br/>docs/refactor/plan.md + plan.json + phases<br/>PR on target"]

    implement --> pickPlan[Pick target plan or implement branch]
    pickPlan --> pickPhases[Pick pending phases]
    pickPhases --> implAgent[Cloud agent]
    implAgent --> implOut["Target: refactor/implement-YYYYMMDD-HHMMSS<br/>code + unit tests<br/>last phase: computer-use walkthrough"]
```

Analyze writes discovery docs on the **legacy** repo and does not open a PR. Plan and Implement write on the **target** repo; Plan opens a PR. Implement runs `test_command` per selected unit-test phase and runs computer-use UI checks only as the last plan phase.
