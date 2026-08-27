# Documentation Rules

## One home per fact

- System topology/current behavior -> `docs/02-system-design.md` or owning subsystem doc.
- Why a choice was made -> ADR.
- How to perform a recurring task -> Skill.
- Repo-wide standing order -> `AGENTS.md`.
- Historical failure -> postmortem.
- Theory -> whitepaper.

## Current-state prose

Architecture docs say how the current system works. Avoid PR chronology, "previously", "now", or temporary migration stories unless the document is explicitly a migration note.

## Code samples

Examples describing public contracts must compile or be covered by a test/fixture once tooling exists. Avoid copied type declarations that can silently drift from code.
