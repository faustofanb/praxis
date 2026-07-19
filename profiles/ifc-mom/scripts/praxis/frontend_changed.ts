/**
 * 前端/PDA 变更分类器。
 *
 * Python 的 verify.py 负责 Git 变更收集和命令编排；这个 Bun 脚本只负责
 * Node 生态更擅长的事情：读取 package.json、判断哪些文件需要 ESLint、
 * 以及 Web monorepo 中哪些 package 可作为显式 typecheck 目标。
 *
 * 输入：stdin JSON，例如 {"kind":"pnpm-web","files":["apps/web-antd/src/a.ts"]}
 * 输出：stdout JSON，例如 {"fullCheck":false,"lintFiles":["..."],"packages":["@vben/web-antd"]}
 */
type Payload = {
  kind: "pnpm-web" | "pnpm-uniapp" | string;
  files: string[];
};

type Result = {
  fullCheck: boolean;
  lintFiles: string[];
  packages: string[];
};

async function stdin(): Promise<string> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of Bun.stdin.stream()) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function packageName(packageJsonPath: string): Promise<string | null> {
  try {
    // Web 是 pnpm monorepo，显式 package typecheck 需要 package name 而不是目录名。
    const packageJson = await Bun.file(packageJsonPath).json();
    return typeof packageJson.name === "string" ? packageJson.name : null;
  } catch {
    // 变更文件可能落在非 package 目录；无法读取 package.json 时跳过。
    return null;
  }
}

function isLintable(file: string): boolean {
  return /\.(cjs|mjs|js|jsx|ts|tsx|vue)$/.test(file);
}

function isFullCheckFile(file: string, kind: string): boolean {
  if (kind === "pnpm-web") {
    // Web 根级配置会影响包解析、类型和构建，提升为 pnpm check。
    return /^(package\.json|pnpm-lock\.yaml|pnpm-workspace\.yaml|turbo\.json|tsconfig.*\.json|eslint\.config\..*|vite\.config\..*)$/.test(file);
  }
  // PDA 没有 monorepo package 识别，根级配置变化时跑项目级 lint + type-check。
  return /^(package\.json|pnpm-lock\.yaml|tsconfig.*\.json|vite\.config\..*|eslint\.config\..*)$/.test(file);
}

async function classify(payload: Payload): Promise<Result> {
  const lintFiles: string[] = [];
  const packages = new Set<string>();
  let fullCheck = false;

  for (const file of payload.files) {
    if (isFullCheckFile(file, payload.kind)) {
      fullCheck = true;
    }

    if (payload.kind === "pnpm-web") {
      if (file.startsWith("apps/web-antd/")) {
        // 当前后台业务应用固定映射到 @vben/web-antd。
        packages.add("@vben/web-antd");
      } else if (file.startsWith("packages/")) {
        const parts = file.split("/");
        if (parts.length >= 2) {
          const name = await packageName(`${parts[0]}/${parts[1]}/package.json`);
          if (name) {
            packages.add(name);
          }
        }
      }
    }

    if (isLintable(file) && await Bun.file(file).exists()) {
      // 只 lint 仍存在的源码文件，避免删除文件导致 ESLint 报路径不存在。
      lintFiles.push(file);
    }
  }

  return {
    fullCheck,
    lintFiles,
    packages: Array.from(packages).sort(),
  };
}

const input = await stdin();
const payload = JSON.parse(input) as Payload;
const result = await classify(payload);
process.stdout.write(JSON.stringify(result));
