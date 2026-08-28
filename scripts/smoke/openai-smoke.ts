/**
 * Non-blocking real-model provider smoke (M2 real_model_eval:
 * "non-blocking provider smoke"). NOT part of any check chain: without
 * OPENAI_API_KEY it prints a skip notice and exits 0.
 *
 * Usage: bun scripts/smoke/openai-smoke.ts [model]
 * Model defaults to PRAXIS_SMOKE_MODEL, then "gpt-4o-mini".
 * Optional PRAXIS_SMOKE_BASE_URL points at any OpenAI-compatible endpoint.
 */
import type { ModelEvent, ModelRequest } from "@praxis/contracts";
import { OpenAIChatProvider } from "@praxis/provider-openai";

const model = process.argv[2] ?? process.env.PRAXIS_SMOKE_MODEL ?? "gpt-4o-mini";
const apiKey = process.env.OPENAI_API_KEY ?? "";
if (apiKey.trim() === "") {
  console.log("smoke:openai skipped — set OPENAI_API_KEY to run the real-model smoke");
  process.exit(0);
}

const provider = new OpenAIChatProvider({
  apiKey,
  ...(process.env.PRAXIS_SMOKE_BASE_URL === undefined
    ? {}
    : { baseUrl: process.env.PRAXIS_SMOKE_BASE_URL }),
});

const request: ModelRequest = {
  model,
  messages: [
    { role: "system", text: "You are a Praxis smoke test. Follow instructions exactly." },
    { role: "user", text: "Reply with exactly: praxis-smoke-ok" },
  ],
  correlationId: "openai-smoke",
};

const controller = new AbortController();
process.on("SIGINT", () => controller.abort());

let text = "";
let finishReason: string | null = null;
const eventTypes: string[] = [];

for await (const event of provider.complete(request, controller.signal)) {
  const summary = summarize(event);
  if (summary !== null) {
    eventTypes.push(summary);
  }
  if (event.type === "textDelta") {
    text += event.text;
  }
  if (event.type === "completed") {
    finishReason = event.finishReason;
  }
  if (event.type === "providerError") {
    console.error(`smoke providerError: ${event.error.kind} — ${event.error.message}`);
    process.exit(1);
  }
}

console.log(`model=${model} events=[${eventTypes.join(", ")}]`);
console.log(`final text: ${text.trim()}`);
if (finishReason === null) {
  console.error("smoke failed: stream ended without a completed event");
  process.exit(1);
}
process.exit(0);

function summarize(event: ModelEvent): string | null {
  switch (event.type) {
    case "textDelta":
      return null;
    case "completed":
      return `completed:${event.finishReason}`;
    case "usage":
      return `usage(in=${event.inputTokens},out=${event.outputTokens})`;
    default:
      return event.type;
  }
}
