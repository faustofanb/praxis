# Repository Bootstrap Checklist

Use this only for M0. After the repository is stable, durable rules live in the technical baseline and AGENTS/rules.

## Environment

- [ ] Install mise.
- [ ] Copy root bootstrap configs.
- [ ] `mise install` resolves Bun 1.3.14.
- [ ] Run first intentional `bun install`; commit `bun.lock`.
- [ ] Generate and commit `mise.lock`.
- [ ] CI verifies locked/frozen installs.

## Workspace skeleton

- [ ] `apps/cli`
- [ ] `packages/contracts`
- [ ] `packages/core`
- [ ] `packages/store-sqlite`
- [ ] `packages/provider-openai`
- [ ] `packages/tools-local`
- [ ] `packages/testkit`

Every package starts with the smallest manifest and exact dependencies. Do not create placeholder managers/services.

## Governance files

- [ ] `AGENTS.md`
- [ ] `.agents/rules/*`
- [ ] `.agents/skills/*`
- [ ] `CONTRIBUTING.md`
- [ ] PR template
- [ ] task issue template
- [ ] ADR-0001 through ADR-0008 accepted

## First CI gates

- [ ] frozen install
- [ ] Biome format/lint
- [ ] TypeScript build/typecheck
- [ ] deterministic unit tests
- [ ] Knip
- [ ] commit message validation

## Bootstrap exit condition

A clean clone using only committed files can reproduce the toolchain and pass `mise run check:all`. No source code feature work begins before this is true.
