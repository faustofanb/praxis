---
name: rtk
description: Use when a task needs shell commands and RTK may optimize command output. Apply the availability check and fallback policy before running shell commands.
---

# RTK Command Optimization

## Policy

RTK is an optional optimization, not a Praxis prerequisite.

1. Before a task needs shell execution, run `rtk --version` or otherwise confirm the `rtk` binary is available.
2. If available, prefer RTK-wrapped commands for supported shell workflows, especially Git and high-output developer commands.
3. If unavailable, run the original command directly and include the literal `RTK optimization unavailable` in delivery.
4. Do not fail, block, or ask the user to install RTK only because the optimization is missing.
5. Never package the RTK binary in Praxis; this skill only defines behavior.

Baseline verified for this package: `rtk 0.42.3`.
