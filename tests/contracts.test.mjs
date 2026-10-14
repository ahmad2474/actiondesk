import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import {
  SCHEMA_FILE, TYPES_FILE, exportSchema, generateArtifacts, writeArtifacts, checkArtifacts,
} from "../scripts/contracts.mjs";

function temporaryDirectory(t) {
  const directory = mkdtempSync(resolve(tmpdir(), "actiondesk-contracts-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  return directory;
}
const comparatorFixture = { [SCHEMA_FILE]: '{"test":"comparator-only"}\n', [TYPES_FILE]: "// Comparator fixture, not generated API output\n" };

test("artifact comparison accepts matching files without modifying them", t => {
  const directory = temporaryDirectory(t);
  writeArtifacts(comparatorFixture, directory);
  assert.doesNotThrow(() => checkArtifacts(comparatorFixture, directory));
  assert.equal(readFileSync(resolve(directory, TYPES_FILE), "utf8"), comparatorFixture[TYPES_FILE]);
});

for (const file of [SCHEMA_FILE, TYPES_FILE]) {
  test(`artifact comparison rejects drift in ${file} without fixing it`, t => {
    const directory = temporaryDirectory(t);
    writeArtifacts(comparatorFixture, directory);
    writeFileSync(resolve(directory, file), "intentional drift\n");
    assert.throws(() => checkArtifacts(comparatorFixture, directory), /API contract drift/);
    assert.equal(readFileSync(resolve(directory, file), "utf8"), "intentional drift\n");
  });
}

test("artifact comparison rejects a missing generated file", t => {
  const directory = temporaryDirectory(t);
  assert.throws(() => checkArtifacts(comparatorFixture, directory), /API contract drift/);
});

let generatorInstalled = true;
try { createRequire(import.meta.url).resolve("openapi-typescript"); }
catch { generatorInstalled = false; }
const needsGenerator = { skip: generatorInstalled ? false : "BLOCKED: openapi-typescript is not installed" };

test("real FastAPI schema generates reproducible TypeScript with intended package", needsGenerator, async t => {
  const directory = temporaryDirectory(t);
  const document = exportSchema();
  assert.deepEqual(Object.keys(document.paths).sort(), ["/approvals", "/auth/login", "/auth/logout", "/auth/me", "/health", "/ready", "/requests", "/requests/{request_id}", "/requests/{request_id}/revisions", "/requests/{request_id}/transitions"]);
  const source = structuredClone(document);
  const first = await generateArtifacts(document);
  assert.deepEqual(document, source);
  assert.deepEqual(await generateArtifacts(document), first);
  assert.match(first[TYPES_FILE], /get_health/);
  assert.match(first[TYPES_FILE], /get_readiness/);
  writeArtifacts(first, directory);
  assert.doesNotThrow(() => checkArtifacts(first, directory));
});

test("a changed exported API field triggers schema and TypeScript drift", needsGenerator, async t => {
  const directory = temporaryDirectory(t);
  const original = exportSchema();
  const first = await generateArtifacts(original);
  writeArtifacts(first, directory);
  const changed = structuredClone(original);
  changed.components.schemas.Health.properties.verification_marker = { type: "integer" };
  changed.components.schemas.Health.required.push("verification_marker");
  const altered = await generateArtifacts(changed);
  assert.notEqual(altered[SCHEMA_FILE], first[SCHEMA_FILE]);
  assert.notEqual(altered[TYPES_FILE], first[TYPES_FILE]);
  assert.throws(() => checkArtifacts(altered, directory), /API contract drift/);
});

test("contract CLI detects tampering and returns a nonzero exit code", needsGenerator, t => {
  const directory = temporaryDirectory(t);
  const cli = (extra = []) => spawnSync(process.execPath,
    ["scripts/contracts.mjs", "--output-dir", directory, ...extra], { encoding: "utf8", env: process.env });
  assert.equal(cli().status, 0);
  assert.equal(cli(["--check"]).status, 0);
  writeFileSync(resolve(directory, TYPES_FILE), "// Intentional type drift\n");
  const drift = cli(["--check"]);
  assert.equal(drift.status, 1);
  assert.match(drift.stderr, /API contract drift/);
  assert.equal(readFileSync(resolve(directory, TYPES_FILE), "utf8"), "// Intentional type drift\n");
});
