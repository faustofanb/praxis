import { packageName as cliPackageName } from "@praxis/cli";
import { packageName as contractsPackageName } from "@praxis/contracts";
import {
  workspaceDependencies as coreDependencies,
  packageName as corePackageName,
} from "@praxis/core";
import {
  workspaceDependencies as providerDependencies,
  packageName as providerPackageName,
} from "@praxis/provider-openai";
import {
  workspaceDependencies as storeDependencies,
  packageName as storePackageName,
} from "@praxis/store-sqlite";
import {
  workspaceDependencies as testkitDependencies,
  packageName as testkitPackageName,
} from "@praxis/testkit";
import {
  workspaceDependencies as toolsDependencies,
  packageName as toolsPackageName,
} from "@praxis/tools-local";
import fc from "fast-check";
import { expect, test } from "vitest";

test("workspace packages resolve and expose their manifest name", () => {
  expect(cliPackageName).toBe("@praxis/cli");
  expect(contractsPackageName).toBe("@praxis/contracts");
  expect(corePackageName).toBe("@praxis/core");
  expect(providerPackageName).toBe("@praxis/provider-openai");
  expect(storePackageName).toBe("@praxis/store-sqlite");
  expect(testkitPackageName).toBe("@praxis/testkit");
  expect(toolsPackageName).toBe("@praxis/tools-local");
});

test("declared workspace dependencies resolve across package boundaries", () => {
  expect([...coreDependencies]).toEqual(["@praxis/contracts"]);
  expect([...storeDependencies]).toEqual(["@praxis/contracts"]);
  expect([...providerDependencies]).toEqual(["@praxis/contracts"]);
  expect([...toolsDependencies]).toEqual(["@praxis/contracts"]);
  expect([...testkitDependencies]).toEqual(["@praxis/contracts", "@praxis/core"]);
});

test("fast-check property runs and holds (square of an integer is non-negative)", () => {
  fc.assert(
    fc.property(fc.integer(), (n) => {
      expect(n * n).toBeGreaterThanOrEqual(0);
    }),
  );
});
