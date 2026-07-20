---
name: praxis-system-development
description: Route a system-development task to the smallest installed method Skill. Use for brainstorming, code review, context degradation or optimization, file/skill search, prompt design, subagent execution, systematic debugging, test writing, or implementation minimalism.
---

# Praxis system development router

Inspect the task intent and load only the matching installed Skill:

- design uncertainty → Brainstorming
- correctness or maintainability review → Code Quality Review
- lost context or conflicting context → Context Degradation
- context budget or excessive instructions → Context Optimization
- repository lookup → File Search
- missing capability discovery → Find Skills
- implementation scope control → Karpathy Guidelines
- prompt construction → Prompt Engineering
- independently executable planned work → Subagent Driven Development
- defects or failing tests → Systematic Debugging
- new or changed tests → Testing Writing Guidelines

Check that the selected Skill is available in the current Agent host. If absent, report the missing Skill instead of reconstructing its full instructions. Never load every delegate by default.
