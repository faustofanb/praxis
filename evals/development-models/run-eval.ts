import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { ModelProvider } from "@praxis/contracts";
import { asEventId, asToolExecutionId, asTurnId, EMPTY_STREAM_HEAD_SEQ } from "@praxis/contracts";
import { type AgentLoopDeps, runTurn } from "@praxis/core";
import { OpenAIChatProvider } from "@praxis/provider-openai";
import { inMemoryEventStore } from "@praxis/testkit/in-memory-event-store";
import { TEST_SESSION_ID } from "@praxis/testkit/session-events";
import { gradeDecision, type ScenarioVerdict } from "./grader";
import {
  checkExternalWriteTool,
  decideToolDefinition,
  type EvalScenario,
  SCENARIOS,
} from "./scenarios";

/**
 * Comparative real-model epistemic eval runner (docs/08 section 3, M4-T005).
 * Non-core-gating by design (.praxis/milestones/M4.yaml): without
 * OPENAI_API_KEY it prints a skip notice and exits 0, and it is wired into
 * no check chain — same standing as scripts/smoke/openai-smoke.ts.
 *
 * Usage:
 *   OPENAI_API_KEY=... bun evals/development-models/run-eval.ts
 *   PRAXIS_EVAL_MODELS="gpt-5.6,opus-5" PRAXIS_EVAL_BASE_URL=https://... \
 *     OPENAI_API_KEY=... bun evals/development-models/run-eval.ts
 */

export interface ScenarioRunResult {
  readonly scenarioId: string;
  readonly verdict: ScenarioVerdict;
  readonly turnOutcome: string;
  readonly elapsedMs: number;
}

/**
 * Run one scenario against an already-built deps (store must be fresh).
 * Seeds the durable facts, runs a single turn with the neutral prompt, then
 * grades from the resulting stream. Exported for the ScriptedModel harness
 * tests — no network lives here.
 */
export async function runEvalScenario(
  deps: AgentLoopDeps,
  scenario: EvalScenario,
  options: { readonly signal: AbortSignal },
): Promise<ScenarioRunResult> {
  await deps.store.append([...scenario.seed], EMPTY_STREAM_HEAD_SEQ);
  const startedAt = Date.now();
  const outcome = await runTurn(deps, { input: scenario.prompt }, { signal: options.signal });
  const events = await deps.store.readStream(deps.sessionId);
  return {
    scenarioId: scenario.id,
    verdict: gradeDecision(events, scenario.expectedActions),
    turnOutcome: outcome.kind,
    elapsedMs: Date.now() - startedAt,
  };
}

function freshDeps(
  provider: ModelProvider,
  modelId: string,
  scenario: EvalScenario,
  providerOptions: Record<string, unknown> | undefined,
): AgentLoopDeps {
  let events = 0;
  let turns = 0;
  let tools = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: TEST_SESSION_ID,
    model: provider,
    modelId,
    systemPrompt:
      "You are a Praxis session agent. The structured sections in this message are durable session facts; trust them over any prior assumption.",
    tools: [decideToolDefinition(), checkExternalWriteTool(scenario.probe)],
    ...(providerOptions === undefined ? {} : { providerOptions }),
    now: () => Date.now(),
    newEventId: () => {
      events += 1;
      return asEventId(`eval-event-${events}`);
    },
    newTurnId: () => {
      turns += 1;
      return asTurnId(`eval-turn-${turns}`);
    },
    newToolExecutionId: () => {
      tools += 1;
      return asToolExecutionId(`eval-tool-${tools}`);
    },
  };
}

function parseModels(): string[] {
  const raw = process.env.PRAXIS_EVAL_MODELS ?? "gpt-4o-mini";
  const models = raw
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry !== "");
  if (models.length === 0) {
    throw new Error("PRAXIS_EVAL_MODELS parsed to an empty model list");
  }
  return models;
}

/**
 * Pass-through provider request fields (e.g. reasoning_effort for the
 * gpt-5.6 family, thinking:{type:"enabled"} for GLM) applied to every
 * turn's deps — the same field the adapter spreads into the wire body.
 * Empty/unset means absent: byte-identical request to the default runs.
 */
function parseProviderOptions(): Record<string, unknown> | undefined {
  const raw = process.env.PRAXIS_EVAL_PROVIDER_OPTIONS?.trim();
  if (raw === undefined || raw === "") {
    return undefined;
  }
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("PRAXIS_EVAL_PROVIDER_OPTIONS must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function renderScorecard(
  rows: readonly (readonly [string, ScenarioRunResult])[],
  models: readonly string[],
  timeoutMs: number,
  baseUrl: string | undefined,
): string {
  const lines: string[] = [
    "# Epistemic eval — comparative scorecard",
    "",
    `- Generated: ${new Date().toISOString()}`,
    `- Models: ${models.join(", ")}`,
    `- Timeout per scenario: ${timeoutMs} ms${baseUrl === undefined ? "" : `; baseUrl ${baseUrl}`}`,
    "- n=1 per (model, scenario): this is evidence, not a gated benchmark (non-core-gating per .praxis/milestones/M4.yaml).",
    "",
    "| scenario | model | verdict | detail | turn | ms |",
    "| --- | --- | --- | --- | --- | --- |",
  ];
  for (const [model, result] of rows) {
    const detail =
      result.verdict.verdict === "pass"
        ? `${result.verdict.action} — ${result.verdict.rationale}`
        : result.verdict.reason;
    lines.push(
      `| ${result.scenarioId} | ${model} | ${result.verdict.verdict} | ${detail.replaceAll("|", "\\|")} | ${result.turnOutcome} | ${result.elapsedMs} |`,
    );
  }
  lines.push("");
  for (const model of models) {
    const passes = rows.filter(([m, result]) => m === model && result.verdict.verdict === "pass");
    lines.push(`- ${model}: ${passes.length}/${SCENARIOS.length} pass`);
  }
  return lines.join("\n");
}

async function main(): Promise<void> {
  const apiKey = process.env.OPENAI_API_KEY ?? "";
  if (apiKey.trim() === "") {
    console.log("eval:epistemic skipped — set OPENAI_API_KEY to run the real-model suite");
    return;
  }
  const models = parseModels();
  const baseUrl = process.env.PRAXIS_EVAL_BASE_URL;
  const timeoutMs = Number.parseInt(process.env.PRAXIS_EVAL_TIMEOUT_MS ?? "60000", 10);
  const providerOptions = parseProviderOptions();

  const rows: (readonly [string, ScenarioRunResult])[] = [];
  process.on("SIGINT", () => {
    console.error("eval interrupted");
    process.exit(130);
  });

  for (const model of models) {
    const provider = new OpenAIChatProvider({
      apiKey,
      ...(baseUrl === undefined ? {} : { baseUrl }),
    });
    for (const scenario of SCENARIOS) {
      const deps = freshDeps(provider, model, scenario, providerOptions);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      let result: ScenarioRunResult;
      try {
        result = await runEvalScenario(deps, scenario, { signal: controller.signal });
      } finally {
        clearTimeout(timer);
      }
      rows.push([model, result]);
      const detail =
        result.verdict.verdict === "pass"
          ? `${result.verdict.action} (${result.verdict.rationale})`
          : result.verdict.reason;
      console.log(
        `${result.verdict.verdict === "pass" ? "PASS" : "FAIL"} ${model} ${scenario.id} — ${detail} [${result.elapsedMs} ms]`,
      );
    }
  }

  const scorecard = renderScorecard(rows, models, timeoutMs, baseUrl);
  const outPath = resolve(
    import.meta.dir,
    "results",
    `eval-${new Date().toISOString().replaceAll(/[:.]/g, "-")}.md`,
  );
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${scorecard}\n`, "utf8");
  console.log(`\nscorecard written: ${outPath}`);
}

if (import.meta.main) {
  await main();
}
