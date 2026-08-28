import { packageName as contractsPackageName } from "@praxis/contracts";
import {
  type FetchLike,
  OpenAIChatProvider,
  type OpenAIChatProviderOptions,
} from "./chat-provider";

export const packageName = "@praxis/provider-openai";
export const workspaceDependencies = [contractsPackageName] as const;

export type { FetchLike, OpenAIChatProviderOptions };
export { OpenAIChatProvider };
