import type { ModelMessage, SessionEventUnion, ToolExecutionId } from "@praxis/contracts";

/**
 * Pure conversation projection (docs/02 section 12): rebuilds the model-side
 * message list from durable facts alone. User input comes from TurnStarted,
 * assistant output from ModelResponseCompleted, tool outcomes from the tool
 * lifecycle events — tool results are quoted verbatim as JSON facts; the
 * projection never re-parses or re-executes anything. Replay-safe: reading
 * this twice from the same stream yields the same messages.
 */

export function projectConversation(events: readonly SessionEventUnion[]): ModelMessage[] {
  const messages: ModelMessage[] = [];
  const callIdByExecution = new Map<ToolExecutionId, string>();

  for (const event of events) {
    switch (event.type) {
      case "TurnStarted": {
        const { input } = event.payload;
        if (input !== undefined) {
          messages.push({ role: "user", text: input });
        }
        break;
      }
      case "ModelResponseCompleted": {
        const { text, toolCalls } = event.payload;
        messages.push({
          role: "assistant",
          ...(text === undefined ? {} : { text }),
          ...(toolCalls.length === 0 ? {} : { toolCalls: toolCalls.map((call) => ({ ...call })) }),
        });
        break;
      }
      case "ToolProposed": {
        const { toolExecutionId, toolCallId } = event.payload;
        if (toolCallId !== undefined) {
          callIdByExecution.set(toolExecutionId, toolCallId);
        }
        break;
      }
      case "ToolSucceeded":
        messages.push(
          toolMessage(callIdByExecution, event.payload.toolExecutionId, {
            status: "succeeded",
            result: safeJson(event.payload.resultJson),
          }),
        );
        break;
      case "ToolRejected":
        messages.push(
          toolMessage(callIdByExecution, event.payload.toolExecutionId, {
            status: "rejected",
            reason: event.payload.reason,
          }),
        );
        break;
      case "ToolFailed":
        messages.push(
          toolMessage(callIdByExecution, event.payload.toolExecutionId, {
            status: "failed",
            message: event.payload.message,
          }),
        );
        break;
      case "ToolIndeterminate":
        messages.push(
          toolMessage(callIdByExecution, event.payload.toolExecutionId, {
            status: "indeterminate",
            reason: event.payload.reason,
          }),
        );
        break;
      default:
        break;
    }
  }
  return messages;
}

function toolMessage(
  callIdByExecution: ReadonlyMap<ToolExecutionId, string>,
  toolExecutionId: ToolExecutionId,
  body: Record<string, unknown>,
): ModelMessage {
  return {
    role: "tool",
    toolCallId: callIdByExecution.get(toolExecutionId) ?? toolExecutionId,
    text: JSON.stringify(body),
  };
}

function safeJson(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}
