# Workflows

Analyze, Plan, and Implement. Each step starts a cloud agent with both repos checked out. Artifacts land on a dated `refactor/*` branch.

```mermaid
flowchart TB
    analyze[Analyze] --> analyzeOut["Legacy branch: refactor/analyze-YYYYMMDD<br/>docs/modernization/*<br/>no PR"]

    analyzeOut --> plan[Plan]
    plan --> pickAnalyze[Pick a legacy analyze branch]
    pickAnalyze --> planOut["Target branch: refactor/plan-YYYYMMDD<br/>docs/refactor/plan.md, plan.json, phases<br/>PR on target"]

    planOut --> implement[Implement]
    implement --> pickPlan[Pick a target plan or implement branch]
    pickPlan --> pickPhases[Pick pending phases]
    pickPhases --> implOut["Target branch: refactor/implement-YYYYMMDD<br/>code + unit tests<br/>last phase: computer-use walkthrough"]
```

- **Analyze** maps the legacy system. Target repo is context only.
- **Plan** reads that analyze branch and writes a phased plan on the target repo.
- **Implement** codes selected phases on the target. Unit tests run first; computer-use UI testing is only the last phase.
