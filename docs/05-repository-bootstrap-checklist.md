# Repository Bootstrap Checklist

Use this only for M0. After the repository is stable, durable rules live in the technical baseline and AGENTS/rules.

## Environment

- [x] Install mise.
- [x] Copy root bootstrap configs.
- [x] `mise install` resolves Bun 1.3.14.
- [x] Run first intentional `bun install`; commit `bun.lock`.
- [x] Generate and commit `mise.lock`.
- [x] CI verifies locked/frozen installs.

## Workspace skeleton

- [x] `apps/cli`
- [x] `packages/contracts`
- [x] `packages/core`
- [x] `packages/store-sqlite`
- [x] `packages/provider-openai`
- [x] `packages/tools-local`
- [x] `packages/testkit`

Every package starts with the smallest manifest and exact dependencies. Do not create placeholder managers/services.

## Governance files

- [x] `AGENTS.md`
- [x] `.agents/rules/*`
- [x] `.agents/skills/*`
- [x] `CONTRIBUTING.md`
- [x] PR template
- [x] task issue template
- [x] ADR-0001 through ADR-0008 accepted

## First CI gates

- [x] frozen install
- [x] Biome format/lint
- [x] TypeScript build/typecheck
- [x] deterministic unit tests
- [x] Knip
- [x] commit message validation

## Bootstrap exit condition

A clean clone using only committed files can reproduce the toolchain and pass `mise run check:all`. No source code feature work begins before this is true.
