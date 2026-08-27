import { packageName as contractsPackageName } from "@praxis/contracts";
import { packageName as corePackageName } from "@praxis/core";

export const packageName = "@praxis/testkit";
export const workspaceDependencies = [contractsPackageName, corePackageName] as const;
