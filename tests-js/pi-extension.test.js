import assert from "node:assert/strict";
import test from "node:test";

import praxisExtension, { splitArguments } from "../pi-extension/index.js";

test("Pi extension registers the Praxis command", () => {
  const commands = new Map();
  praxisExtension({
    registerCommand(name, definition) {
      commands.set(name, definition);
    },
  });

  assert.deepEqual([...commands.keys()], ["praxis"]);
  assert.match(commands.get("praxis").description, /Praxis V2 CLI/);
});

test("Pi extension parses quoted CLI arguments without a shell", () => {
  assert.deepEqual(
    splitArguments("requirement create '挤压 工序' \"原始 request\""),
    ["requirement", "create", "挤压 工序", "原始 request"],
  );
  assert.throws(() => splitArguments("requirement 'unfinished"), /Unclosed quote/);
});
