import type { ModelMessage, ModelToolDefinition } from "@praxis/contracts";
import type { ContextBudget } from "./budget";
import { DEFAULT_CONTEXT_BUDGET, validateContextBudget } from "./budget";

/**
 * v0 deterministic ContextBuilder (docs/02 section 12, docs/03 M2.2).
 * Pure projection: same input and budget always build the same context.
 * No clock, randomness, environment reads, or I/O. Model-generated
 * summarization and semantic retrieval are deferred by design; messages
 * that fall out of the window are compacted into a deterministic count
 * recap (M5-T002) instead of vanishing silently.
 *
 * Truncation keeps the head of a fragment and appends a `…[+N bytes
 * truncated]` marker. Truncated assistant tool arguments are context
 * display only — executable tool state lives in the event store and is
 * never re-parsed from context.
 */

const TEXT_ENCODER = new TextEncoder();
const TRUNCATION_RESERVE_BYTES = 40;

function utf8Bytes(text: string): number {
  return TEXT_ENCODER.encode(text).length;
}

function cutToBytes(text: string, limitBytes: number): string {
  let kept = "";
  let bytes = 0;
  for (const char of text) {
    const charBytes = utf8Bytes(char);
    if (bytes + charBytes > limitBytes) {
      break;
    }
    kept += char;
    bytes += charBytes;
  }
  return kept;
}

type FittedText = {
  readonly text: string;
  readonly cutBytes: number;
};

function fitText(text: string, maxBytes: number): FittedText {
  const bytes = utf8Bytes(text);
  if (bytes <= maxBytes) {
    return { text, cutBytes: 0 };
  }
  const kept = cutToBytes(text, maxBytes - TRUNCATION_RESERVE_BYTES);
  const cutBytes = bytes - utf8Bytes(kept);
  return { text: `${kept}…[+${cutBytes} bytes truncated]`, cutBytes };
}

export type ContextBuildInput = {
  readonly systemPrompt: string;
  /**
   * Structured epistemic brief (docs/02 section 12.2), pre-rendered by
   * projectEpistemicBrief. Composed into the single system fragment with a
   * blank-line separator; undefined leaves the system prompt untouched.
   */
  readonly epistemicBrief?: string;
  readonly history: readonly ModelMessage[];
  readonly tools?: readonly ModelToolDefinition[];
};

export type ContextEstimate = {
  readonly totalBytes: number;
  readonly estimatedTokens: number;
  readonly droppedMessages: number;
  readonly truncatedFragments: number;
};

export type BuiltContext = {
  readonly messages: readonly ModelMessage[];
  readonly tools: readonly ModelToolDefinition[];
  readonly estimate: ContextEstimate;
};

export class InvalidContextError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidContextError";
  }
}

export class ContextBudgetExceededError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContextBudgetExceededError";
  }
}

function messageBytes(message: ModelMessage): number {
  switch (message.role) {
    case "system":
    case "user":
      return utf8Bytes(message.text);
    case "assistant":
      return (
        utf8Bytes(message.text ?? "") +
        (message.toolCalls ?? []).reduce(
          (sum, call) =>
            sum + utf8Bytes(call.id) + utf8Bytes(call.name) + utf8Bytes(call.argumentsJson),
          0,
        )
      );
    case "tool":
      return utf8Bytes(message.toolCallId) + utf8Bytes(message.text);
  }
}

function toolBytes(tool: ModelToolDefinition): number {
  return utf8Bytes(tool.name) + utf8Bytes(tool.description) + utf8Bytes(tool.parametersJson);
}

type FittedMessage = {
  readonly message: ModelMessage;
  readonly truncatedFragments: number;
};

function fitHistoryMessage(message: ModelMessage, budget: ContextBudget): FittedMessage {
  switch (message.role) {
    case "user": {
      const fitted = fitText(message.text, budget.maxFragmentBytes);
      return {
        message: { role: "user", text: fitted.text },
        truncatedFragments: fitted.cutBytes > 0 ? 1 : 0,
      };
    }
    case "assistant": {
      let truncatedFragments = 0;
      const text =
        message.text === undefined ? undefined : fitText(message.text, budget.maxFragmentBytes);
      if (text !== undefined && text.cutBytes > 0) {
        truncatedFragments += 1;
      }
      const toolCalls = message.toolCalls?.map((call) => {
        const fittedArguments = fitText(call.argumentsJson, budget.maxFragmentBytes);
        if (fittedArguments.cutBytes > 0) {
          truncatedFragments += 1;
        }
        return { ...call, argumentsJson: fittedArguments.text };
      });
      const fitted: ModelMessage = {
        role: "assistant",
        ...(text === undefined ? {} : { text: text.text }),
        ...(toolCalls === undefined ? {} : { toolCalls }),
      };
      return { message: fitted, truncatedFragments };
    }
    case "tool": {
      const fitted = fitText(message.text, budget.maxToolResultBytes);
      return {
        message: { role: "tool", toolCallId: message.toolCallId, text: fitted.text },
        truncatedFragments: fitted.cutBytes > 0 ? 1 : 0,
      };
    }
    case "system":
      throw new InvalidContextError(
        "history must not contain system messages; the system fragment comes from systemPrompt only",
      );
  }
}

/**
 * Deterministic compaction recap (docs/02 section 12.3, M5-T002): one
 * structured section appended to the system fragment when messages drop out
 * of the context window. Counts derive purely from the dropped messages;
 * no clock, randomness, or model-generated prose. Durable events are never
 * deleted — compaction bounds the working context only.
 */
function renderCompactionRecap(
  fittedHistory: readonly FittedMessage[],
  keptCount: number,
  budget: ContextBudget,
): string {
  const dropped = fittedHistory.slice(0, fittedHistory.length - keptCount);
  let user = 0;
  let assistant = 0;
  let tool = 0;
  for (const { message } of dropped) {
    if (message.role === "user") {
      user += 1;
    } else if (message.role === "assistant") {
      assistant += 1;
    } else if (message.role === "tool") {
      tool += 1;
    }
  }
  const countsLine = `${dropped.length} earlier messages compacted: ${user} user, ${assistant} assistant, ${tool} tool results`;
  return `## Compacted history\n${fitText(countsLine, budget.maxFragmentBytes).text}`;
}

export function buildContext(
  input: ContextBuildInput,
  budget: ContextBudget = DEFAULT_CONTEXT_BUDGET,
): BuiltContext {
  validateContextBudget(budget);

  const baseSystemPrompt =
    input.epistemicBrief === undefined
      ? input.systemPrompt
      : `${input.systemPrompt}\n\n${input.epistemicBrief}`;

  const fittedHistory = input.history.map((message) => fitHistoryMessage(message, budget));
  const windowStart = Math.max(0, fittedHistory.length - budget.maxRecentMessages);
  let window = fittedHistory.slice(windowStart);

  const tools = input.tools ?? [];
  const toolTotalBytes = tools.reduce((sum, tool) => sum + toolBytes(tool), 0);

  let historyTruncatedFragments = 0;
  for (const fitted of fittedHistory) {
    historyTruncatedFragments += fitted.truncatedFragments;
  }

  while (true) {
    const droppedMessages = fittedHistory.length - window.length;
    const recapSection =
      droppedMessages > 0 ? renderCompactionRecap(fittedHistory, window.length, budget) : null;
    const composedSystemPrompt =
      recapSection === null ? baseSystemPrompt : `${baseSystemPrompt}\n\n${recapSection}`;
    if (
      input.epistemicBrief !== undefined &&
      utf8Bytes(composedSystemPrompt) > budget.maxFragmentBytes
    ) {
      // Tail-truncating the composed fragment could silently cut the brief's
      // non-compactable sections (docs/02 section 12.2) or the compaction
      // recap; with facts present the build fails closed instead. Without a
      // brief the v0 head-truncation of a lone oversized prompt still applies.
      throw new ContextBudgetExceededError(
        `system prompt plus epistemic brief reach ${utf8Bytes(composedSystemPrompt)} bytes over the fragment cap of ${budget.maxFragmentBytes}; refusing to truncate structured non-compactable state`,
      );
    }
    const fittedSystem = fitText(composedSystemPrompt, budget.maxFragmentBytes);
    const systemMessage: ModelMessage = {
      role: "system",
      text: fittedSystem.text,
    };
    const truncatedFragments = historyTruncatedFragments + (fittedSystem.cutBytes > 0 ? 1 : 0);

    const totalBytes =
      messageBytes(systemMessage) +
      window.reduce((sum, fitted) => sum + messageBytes(fitted.message), 0) +
      toolTotalBytes;
    const estimatedTokens = Math.ceil(totalBytes / 4);
    if (estimatedTokens <= budget.maxEstimatedTokens) {
      return {
        messages: [systemMessage, ...window.map((fitted) => fitted.message)],
        tools,
        estimate: {
          totalBytes,
          estimatedTokens,
          droppedMessages,
          truncatedFragments,
        },
      };
    }
    if (window.length <= 1) {
      throw new ContextBudgetExceededError(
        window.length === 0
          ? `system prompt alone estimates ${estimatedTokens} tokens over the cap of ${budget.maxEstimatedTokens}`
          : `system prompt plus the trailing message estimate ${estimatedTokens} tokens over the cap of ${budget.maxEstimatedTokens}; refusing to drop the trailing message`,
      );
    }
    window = window.slice(1);
  }
}
