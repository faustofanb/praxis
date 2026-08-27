# Praxis AI Development Controller

The repository should expose these commands through mise once M0 creates the real workspace:

```text
ai:status   show current machine-readable project state
ai:brief    build bounded task context for the coding AI
ai:plan     validate a Task Contract and transition to PLAN_READY
ai:guard    check diff scope, architecture boundaries and dependency rules
ai:verify   derive required gates from the real diff and execute them
ai:accept   evaluate task/milestone acceptance evidence
ai:handoff  persist a stable cross-session handoff
```

`praxis-dev.ts` in this baseline is a bootstrap specification/skeleton. During M0 it must be made executable and tested before feature development begins.
