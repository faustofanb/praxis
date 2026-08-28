import type { ModelEvent, ModelProvider, ModelRequest } from "@praxis/contracts";

/**
 * Deterministic model provider for correctness gates (docs/02 section 4.6,
 * ADR-0010). Each `complete()` call consumes the next script and streams its
 * events in order. No clock, no randomness, no I/O.
 */

export type ScriptItem = { kind: "event"; event: ModelEvent } | { kind: "waitForAbort" };

export class ScriptedModelProvider implements ModelProvider {
  #requests: ModelRequest[] = [];
  #scripts: (readonly ScriptItem[])[];
  #nextScript = 0;

  constructor(script: readonly ScriptItem[], ...moreScripts: (readonly ScriptItem[])[]) {
    this.#scripts = [script, ...moreScripts];
  }

  get requests(): readonly ModelRequest[] {
    return this.#requests;
  }

  async *complete(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent> {
    this.#requests.push(request);
    if (signal.aborted) return;

    const script = this.#scripts[this.#nextScript];
    if (script === undefined) {
      throw new Error(
        `ScriptedModelProvider script exhausted: ${
          this.#nextScript
        } complete() call(s) consumed all ${
          this.#scripts.length
        } script(s); add another script or fix the loop under test`,
      );
    }
    this.#nextScript += 1;

    for (const item of script) {
      if (signal.aborted) return;
      if (item.kind === "waitForAbort") {
        await abortPromise(signal);
        return;
      }
      yield item.event;
    }
  }
}

function abortPromise(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    signal.addEventListener(
      "abort",
      () => {
        resolve();
      },
      { once: true },
    );
  });
}
