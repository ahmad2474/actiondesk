import { defineConfig, globalIgnores } from "eslint/config";
import { fileURLToPath } from "node:url";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
export default defineConfig([...nextVitals, ...nextTs, { settings: { next: { rootDir: fileURLToPath(new URL(".", import.meta.url)) } } }, globalIgnores([".next/**", "next-env.d.ts"])]);
