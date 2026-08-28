import { packageName as contractsPackageName } from "@praxis/contracts";
import { packageName as corePackageName } from "@praxis/core";
import type { ScriptItem } from "./scripted-model";
import { ScriptedModelProvider } from "./scripted-model";

export const packageName = "@praxis/testkit";
export const workspaceDependencies = [contractsPackageName, corePackageName] as const;

export type { ScriptItem };
export { ScriptedModelProvider };
