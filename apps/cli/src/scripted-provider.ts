import type { ModelEvent, ModelProvider, ModelRequest } from "@praxis/contracts";
import { ModelEventSchema } from "@praxis/contracts";

/**
 * Deterministic script-file model provider owned by the CLI composition
 * root. apps-cli must not depend on @praxis/testkit (architecture.yaml), and
 * the M2 human demo must run without network — so the CLI ships its own
 * provider that streams scripts from a JSON file.
 *
 * File shape: an array of scripts; each script is an array of normalized
 * model stream events (validated through ModelEventSchema — the file is an
 * untrusted boundary). Each `complete()` call consumes the next script.
 */

export class ScriptFileModelProvider implements ModelProvider {
  readonly #scripts: readonly (readonly ModelEvent[])[];
  #nextScript = 0;
  #requests: ModelRequest[] = [];

  constructor(
    rawScripts: unknown,
    private readonly source: string,
  ) {
    if (!Array.isArray(rawScripts)) {
      throw new Error(`${source}: expected a JSON array of scripts`);
    }
    this.#scripts = rawScripts.map((script, index) => {
      if (!Array.isArray(script)) {
        throw new Error(`${source}: script #${index} must be an array of model events`);
      }
      return script.map((event) => ModelEventSchema.parse(event));
    });
  }

  get requests(): readonly ModelRequest[] {
    return this.#requests;
  }

  async *complete(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent> {
    this.#requests.push(request);
    if (signal.aborted) {
      return;
    }
    const script = this.#scripts[this.#nextScript];
    if (script === undefined) {
      throw new Error(
        `${this.source}: script exhausted after ${this.#nextScript} complete() call(s); ` +
          "add another script or fix the script file",
      );
    }
    this.#nextScript += 1;
    for (const event of script) {
      if (signal.aborted) {
        return;
      }
      yield event;
    }
  }
}
