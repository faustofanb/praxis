import type { ModelEvent } from "./events";
import type { ModelRequest } from "./request";

/**
 * Model provider port (docs/02 section 10, ADR-0010).
 *
 * Contract rules every implementation must honor:
 *
 * - `complete` returns a cold async iterable; Core consumes it once.
 * - Cancellation is cooperative: when `signal` aborts, the stream simply
 *   ends — no `completed`, no `providerError`, and no throw from a clean
 *   abort. Adapters normalize AbortError into this silent-end shape.
 * - Abnormal provider failures surface as a terminal `providerError` event
 *   with a normalized kind and retryable flag, not as thrown exceptions.
 * - The adapter owns provider-specific retry; Core only reacts to the
 *   normalized failure facts it emitted.
 */
export interface ModelProvider {
  complete(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
}
