import type {
  ModelEvent,
  ModelFinishReason,
  ModelProvider,
  ModelProviderErrorInfo,
  ModelRequest,
  ModelToolDefinition,
} from "@praxis/contracts";
import { WireChunkSchema, WireErrorBodySchema, type WireToolCallDelta } from "./wire-schemas";

/**
 * OpenAI-compatible Chat Completions adapter (docs/02 section 4.4,
 * ADR-0010). Wire format verified against the openai-node types generated
 * from the OpenAPI spec; every other OpenAI-compatible endpoint (vLLM,
 * Ollama, OpenRouter, DeepSeek, ...) speaks the same shape via --base-url.
 *
 * Contract rules honored here:
 * - `complete` returns a cold async generator; nothing is fetched until the
 *   first `next()`.
 * - Abnormal failures surface as one terminal `providerError` event with a
 *   normalized {kind, retryable}; the consumer is never thrown at.
 * - The adapter owns retry for retryable kinds (network, rateLimit,
 *   overloaded, timeout) with exponential backoff; non-retryable kinds
 *   (auth, invalidRequest, unknown) surface immediately.
 * - Cancellation is cooperative: once the caller's signal aborts, the stream
 *   ends silently — no `completed`, no `providerError`, no throw. A read
 *   timeout is distinct from caller cancellation and maps to kind `timeout`.
 */

/** Minimal structural fetch type: Bun/Node's global fetch satisfies it. */
export type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export type OpenAIChatProviderOptions = {
  readonly apiKey: string;
  /** Chat Completions root, e.g. https://api.openai.com/v1 (default). */
  readonly baseUrl?: string;
  readonly fetchImpl?: FetchLike;
  readonly sleep?: (ms: number) => Promise<void>;
  /** Retryable failures are retried up to this many times (default 2). */
  readonly maxRetries?: number;
  /** Backoff base for retry attempt n: initial * 2^n ms (default 500). */
  readonly initialRetryDelayMs?: number;
  /** Per-attempt read timeout (default 120s); caller abort always wins. */
  readonly timeoutMs?: number;
};

const DEFAULT_BASE_URL = "https://api.openai.com/v1";
const DEFAULT_MAX_RETRIES = 2;
const DEFAULT_INITIAL_RETRY_DELAY_MS = 500;
const DEFAULT_TIMEOUT_MS = 120_000;

type ChatToolCall = {
  readonly id: string;
  readonly type: "function";
  readonly function: { readonly name: string; readonly arguments: string };
};

type ChatMessage =
  | { readonly role: "system"; readonly content: string }
  | { readonly role: "user"; readonly content: string }
  | {
      readonly role: "assistant";
      readonly content?: string;
      readonly tool_calls?: readonly ChatToolCall[];
    }
  | { readonly role: "tool"; readonly tool_call_id: string; readonly content: string };

export class OpenAIChatProvider implements ModelProvider {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly maxRetries: number;
  private readonly initialRetryDelayMs: number;
  private readonly timeoutMs: number;

  constructor(options: OpenAIChatProviderOptions) {
    if (options.apiKey.trim() === "") {
      throw new Error("OpenAIChatProvider requires a non-empty apiKey");
    }
    if (
      options.maxRetries !== undefined &&
      (!Number.isInteger(options.maxRetries) || options.maxRetries < 0)
    ) {
      throw new Error("maxRetries must be a non-negative integer");
    }
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.sleep =
      options.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.initialRetryDelayMs = options.initialRetryDelayMs ?? DEFAULT_INITIAL_RETRY_DELAY_MS;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  complete(request: ModelRequest, signal: AbortSignal): AsyncGenerator<ModelEvent> {
    return this.streamWithRetry(request, signal);
  }

  /**
   * Drive one attempt at a time so a retryable failure can discard the
   * attempt (releasing its response body) and start over; events of a
   * successful attempt are forwarded as they arrive, never buffered.
   * Discarding is only honest while nothing has escaped to the consumer:
   * once any event is delivered, the stream can never be replayed without
   * the consumer assembling events of two attempts, so the failure is
   * surfaced instead of retried.
   */
  private async *streamWithRetry(
    request: ModelRequest,
    signal: AbortSignal,
  ): AsyncGenerator<ModelEvent> {
    for (let attempt = 0; ; attempt += 1) {
      const iterator = this.attemptOnce(request, signal);
      let mustRetry = false;
      let escaped = false;
      for (;;) {
        const result = await iterator.next();
        if (result.done) {
          return;
        }
        const event = result.value;
        if (
          event.type === "providerError" &&
          event.error.retryable &&
          !escaped &&
          attempt < this.maxRetries &&
          !signal.aborted
        ) {
          mustRetry = true;
          break;
        }
        yield event;
        escaped = true;
        if (event.type === "providerError" || event.type === "completed") {
          return;
        }
      }
      await iterator.return?.(undefined);
      if (!mustRetry) {
        return;
      }
      await this.abortableSleep(this.initialRetryDelayMs * 2 ** attempt, signal);
      if (signal.aborted) {
        return;
      }
    }
  }

  /** One HTTP attempt: either streams normalized events or yields one
   *  terminal providerError. Caller cancellation ends the stream silently. */
  private async *attemptOnce(
    request: ModelRequest,
    signal: AbortSignal,
  ): AsyncGenerator<ModelEvent> {
    const timeoutSignal = AbortSignal.any([signal, AbortSignal.timeout(this.timeoutMs)]);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${this.apiKey}`,
          "content-type": "application/json",
          accept: "text/event-stream",
        },
        body: JSON.stringify(toChatRequestBody(request)),
        signal: timeoutSignal,
      });
    } catch (error) {
      const failure = classifyTransportError(error, signal);
      if (failure === null) {
        return;
      }
      yield { type: "providerError", error: failure };
      return;
    }

    if (!response.ok) {
      yield { type: "providerError", error: await classifyHttpFailure(response) };
      return;
    }

    yield* streamChatChunks(response, signal);
  }

  /** Resolves on the delay or on abort, whichever comes first; never rejects. */
  private async abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
    await new Promise<void>((resolve) => {
      let settled = false;
      const settle = () => {
        if (settled) {
          return;
        }
        settled = true;
        signal.removeEventListener("abort", onAbort);
        resolve();
      };
      const onAbort = () => settle();
      signal.addEventListener("abort", onAbort);
      void this.sleep(ms).then(() => settle());
    });
  }
}

function toChatMessages(request: ModelRequest): ChatMessage[] {
  const messages: ChatMessage[] = [];
  for (const message of request.messages) {
    if (message.role === "system") {
      messages.push({ role: "system", content: message.text });
      continue;
    }
    if (message.role === "user") {
      messages.push({ role: "user", content: message.text });
      continue;
    }
    if (message.role === "tool") {
      // OpenAI wire law: each tool_call_id is answered exactly once,
      // immediately after the assistant message that made the call. Durable
      // facts may carry SEVERAL verdicts for one execution (the honest
      // indeterminate, then the later reconciliation — core emits both, in
      // order, never instead of each other), so consecutive same-id tool
      // messages merge into one response whose content is the verbatim fact
      // bodies in event order. Different ids (parallel calls) stay separate.
      const previous = messages.at(-1);
      if (
        previous !== undefined &&
        previous.role === "tool" &&
        previous.tool_call_id === message.toolCallId
      ) {
        const merged: ChatMessage = {
          ...previous,
          content: appendToolFact(previous.content, message.text),
        };
        messages[messages.length - 1] = merged;
        continue;
      }
      messages.push({ role: "tool", tool_call_id: message.toolCallId, content: message.text });
      continue;
    }
    const toolCalls = message.toolCalls?.map(
      (call): ChatToolCall => ({
        id: call.id,
        type: "function",
        function: { name: call.name, arguments: call.argumentsJson },
      }),
    );
    messages.push({
      role: "assistant",
      ...(message.text === undefined ? {} : { content: message.text }),
      ...(toolCalls === undefined ? {} : { tool_calls: toolCalls }),
    });
  }
  return messages;
}

/** The first fact for an id keeps the bare body; later facts turn the
 *  content into a JSON array of bodies (event order preserved). */
function appendToolFact(existing: string, next: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(existing) as unknown;
  } catch {
    parsed = undefined;
  }
  if (Array.isArray(parsed)) {
    return JSON.stringify([...parsed, safeParse(next)]);
  }
  if (parsed === undefined) {
    return JSON.stringify([existing, next]);
  }
  return JSON.stringify([parsed, safeParse(next)]);
}

function safeParse(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

function toChatTools(tools: readonly ModelToolDefinition[]): unknown {
  return tools.map((tool) => ({
    type: "function",
    function: {
      name: tool.name,
      description: tool.description,
      parameters: JSON.parse(tool.parametersJson),
    },
  }));
}

/**
 * providerOptions is the bounded escape hatch (ADR-0010) and merges last —
 * except the streaming keys: the port only offers streaming, so an adapter
 * consumer cannot silently de-stream the request.
 */
function toChatRequestBody(request: ModelRequest): Record<string, unknown> {
  const messages = toChatMessages(request);
  if (messages.length === 0) {
    throw new Error("ModelRequest must carry at least one message");
  }
  return {
    model: request.model,
    messages,
    ...(request.tools === undefined ? {} : { tools: toChatTools(request.tools) }),
    ...(request.maxOutputTokens === undefined
      ? {}
      : { max_completion_tokens: request.maxOutputTokens }),
    ...(request.providerOptions ?? {}),
    stream: true,
    stream_options: { include_usage: true },
  };
}

/** Map the SSE body onto ModelEvents; chat completions only signals the end
 *  of a tool call via finish_reason, so toolCallEnd/completed are emitted
 *  after the stream settles (usage arrives last, completed stays terminal). */
async function* streamChatChunks(
  response: Response,
  callerSignal: AbortSignal,
): AsyncGenerator<ModelEvent> {
  if (response.body === null) {
    yield malformed("model stream had no body");
    return;
  }
  const openCalls: string[] = [];
  const callIds = new Map<number, string>();
  let finishReason: string | undefined;
  let usage: { inputTokens: number; outputTokens: number } | undefined;

  try {
    for await (const payload of sseDataPayloads(response.body)) {
      if (payload === "[DONE]") {
        break;
      }
      const json = parseJson(payload);
      if (!json.ok) {
        yield malformed(`data line is not JSON: ${json.error}`);
        return;
      }
      const chunk = WireChunkSchema.safeParse(json.value);
      if (!chunk.success) {
        yield malformed(summarizeIssues(chunk.error.issues));
        return;
      }
      if (chunk.data.usage != null) {
        usage = {
          inputTokens: chunk.data.usage.prompt_tokens,
          outputTokens: chunk.data.usage.completion_tokens,
        };
      }
      for (const choice of chunk.data.choices) {
        if (choice.delta.content != null && choice.delta.content !== "") {
          yield { type: "textDelta", text: choice.delta.content };
        }
        for (const fragment of choice.delta.tool_calls ?? []) {
          const result = applyToolCallFragment(fragment, openCalls, callIds);
          if ("error" in result) {
            yield malformed(result.error);
            return;
          }
          for (const event of result.events) {
            yield event;
          }
        }
        if (choice.finish_reason != null && finishReason === undefined) {
          finishReason = choice.finish_reason;
        }
      }
    }
  } catch (error) {
    const failure = classifyTransportError(error, callerSignal);
    if (failure === null) {
      return;
    }
    yield { type: "providerError", error: failure };
    return;
  }

  if (finishReason === undefined) {
    yield malformed("stream ended without finish_reason");
    return;
  }
  const mapped = mapFinishReason(finishReason);
  if (mapped === null) {
    yield {
      type: "providerError",
      error: {
        kind: "unknown",
        retryable: false,
        message: `unsupported finish_reason: ${finishReason}`,
      },
    };
    return;
  }
  for (const toolCallId of openCalls) {
    yield { type: "toolCallEnd", toolCallId };
  }
  if (usage !== undefined) {
    yield { type: "usage", ...usage };
  }
  yield { type: "completed", finishReason: mapped };
}

/**
 * Chat completions addresses tool calls by wire index; the first fragment
 * for an index must carry id and name (per the OpenAPI-generated types),
 * later fragments continue the arguments. Returns the events to emit, or an
 * error string on shape violations instead of guessing.
 */
type FragmentResult = { readonly events: readonly ModelEvent[] } | { readonly error: string };

function applyToolCallFragment(
  fragment: WireToolCallDelta,
  openCalls: string[],
  callIds: Map<number, string>,
): FragmentResult {
  const events: ModelEvent[] = [];
  let toolCallId = callIds.get(fragment.index);
  if (toolCallId === undefined) {
    const name = fragment.function?.name;
    if (fragment.id === undefined || name === undefined) {
      return { error: `tool call fragment ${fragment.index} arrived without id and name` };
    }
    toolCallId = fragment.id;
    callIds.set(fragment.index, toolCallId);
    openCalls.push(toolCallId);
    events.push({ type: "toolCallStart", toolCallId, name });
  }
  const argumentsDelta = fragment.function?.arguments;
  if (argumentsDelta != null && argumentsDelta !== "") {
    events.push({ type: "toolCallDelta", toolCallId, argumentsDelta });
  }
  return { events };
}

function mapFinishReason(reason: string): ModelFinishReason | null {
  if (reason === "stop") {
    return "stop";
  }
  if (reason === "tool_calls") {
    return "toolCalls";
  }
  if (reason === "length") {
    return "length";
  }
  return null;
}

/** SSE framing: `data: <payload>` lines, comments and other fields ignored. */
async function* sseDataPayloads(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const payload = dataPayload(buffer.slice(0, newlineIndex));
        if (payload !== undefined) {
          yield payload;
        }
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");
      }
    }
    const tailPayload = dataPayload(buffer + decoder.decode());
    if (tailPayload !== undefined) {
      yield tailPayload;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

function dataPayload(line: string): string | undefined {
  if (!line.startsWith("data:")) {
    return undefined;
  }
  return line.startsWith("data: ") ? line.slice(6) : line.slice(5);
}

/**
 * Abort classification: if the caller's signal fired, this is cooperative
 * cancellation and the stream must end silently (null); only an abort the
 * caller did not request is our read timeout. Everything else a fetch can
 * throw before/during the request is a network failure.
 */
function classifyTransportError(
  error: unknown,
  callerSignal: AbortSignal,
): ModelProviderErrorInfo | null {
  if (callerSignal.aborted) {
    return null;
  }
  if (isAbortError(error)) {
    return { kind: "timeout", retryable: true, message: "model request timed out" };
  }
  return { kind: "network", retryable: true, message: describeError(error) };
}

async function classifyHttpFailure(response: Response): Promise<ModelProviderErrorInfo> {
  const raw = await response.text().catch(() => "");
  const parsed = parseJson(raw);
  const detail =
    parsed.ok && parsed.value !== null && typeof parsed.value === "object"
      ? WireErrorBodySchema.safeParse(parsed.value)
      : { success: false as const };
  const message =
    detail.success && detail.data.error?.message !== undefined
      ? detail.data.error.message
      : truncate(raw, 200);
  const suffix = message === "" ? "" : `: ${message}`;
  const { kind, retryable } = classifyStatus(response.status);
  return {
    kind,
    retryable,
    message: `chat completions request failed with HTTP ${response.status}${suffix}`,
  };
}

function classifyStatus(status: number): Pick<ModelProviderErrorInfo, "kind" | "retryable"> {
  if (status === 401 || status === 403) {
    return { kind: "auth", retryable: false };
  }
  if (status === 429) {
    return { kind: "rateLimit", retryable: true };
  }
  if (status >= 500) {
    return { kind: "overloaded", retryable: true };
  }
  return { kind: "invalidRequest", retryable: false };
}

function malformed(message: string): ModelEvent {
  return {
    type: "providerError",
    error: { kind: "unknown", retryable: false, message: `malformed model output: ${message}` },
  };
}

function summarizeIssues(issues: readonly { path: PropertyKey[]; message: string }[]): string {
  return truncate(
    issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; "),
    200,
  );
}

type JsonParseResult = { ok: true; value: unknown } | { ok: false; error: string };

function parseJson(text: string): JsonParseResult {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (error) {
    return { ok: false, error: describeError(error) };
  }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}
