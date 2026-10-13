import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const SCHEMA_FILE = "packages/contracts/openapi.json";
export const TYPES_FILE = "packages/contracts/src/api.d.ts";

export function exportSchema() {
  const python = process.env.CONTRACT_PYTHON;
  const result = spawnSync(python ?? "uv", python
    ? ["scripts/export_openapi.py", "--stdout"]
    : ["run", "--frozen", "python", "scripts/export_openapi.py", "--stdout"], {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, UV_CACHE_DIR: resolve(ROOT, ".cache/uv") },
  });
  if (result.error || result.status !== 0) {
    throw new Error(result.error?.message || result.stderr || "FastAPI OpenAPI export failed");
  }
  return JSON.parse(result.stdout);
}

export async function generateArtifacts(document) {
  // Use the approved generator only: dependency failures are never converted
  // into a hand-written or partial TypeScript schema fallback.
  const { default: openapiTS, astToString } = await import("openapi-typescript");
  const ast = await openapiTS(document);
  return {
    [SCHEMA_FILE]: JSON.stringify(document, null, 2) + "\n",
    [TYPES_FILE]: "// Generated from FastAPI OpenAPI. Run make contracts; do not edit.\n"
      + astToString(ast),
  };
}

export function writeArtifacts(outputs, outputDir = ROOT) {
  for (const [name, content] of Object.entries(outputs)) {
    const path = resolve(outputDir, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
}

export function checkArtifacts(outputs, outputDir = ROOT) {
  const drifted = [];
  for (const [name, expected] of Object.entries(outputs)) {
    try {
      if (readFileSync(resolve(outputDir, name), "utf8") !== expected) drifted.push(name);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      drifted.push(name);
    }
  }
  if (drifted.length) {
    throw new Error(`API contract drift: ${drifted.join(", ")}. Run make contracts and review the diff.`);
  }
}

async function main() {
  let check = false;
  let outputDir = ROOT;
  for (let i = 2; i < process.argv.length; i++) {
    const argument = process.argv[i];
    if (argument === "--check") check = true;
    else if (argument === "--output-dir" && process.argv[i + 1]) outputDir = resolve(process.argv[++i]);
    else throw new Error(`Unknown or incomplete argument: ${argument}`);
  }
  const outputs = await generateArtifacts(exportSchema());
  if (check) checkArtifacts(outputs, outputDir);
  else writeArtifacts(outputs, outputDir);
  console.log(check ? "Contracts match FastAPI OpenAPI." : "Contracts generated with openapi-typescript.");
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
