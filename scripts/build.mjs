#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = JSON.parse(readFileSync(join(appDir, "package.json"), "utf8"));
const productName = "Jack Codex 工具";
const output = "release";

writeFileSync(
  join(appDir, "variant.json"),
  JSON.stringify({ variant: "jack-codex", appName: productName, version: pkg.version }, null, 2) + "\n",
  "utf8",
);

const runNode = (entry, args = []) => execFileSync(process.execPath, [entry, ...args], {
  cwd: appDir,
  stdio: "inherit",
});

runNode(join(appDir, "node_modules", "vite", "bin", "vite.js"), ["build"]);

const buildConfig = {
  ...(pkg.build || {}),
  appId: "com.jack.codex",
  productName,
  directories: { ...((pkg.build && pkg.build.directories) || {}), output },
  afterPack: "scripts/after-pack.js",
  win: {
    ...((pkg.build && pkg.build.win) || {}),
    signAndEditExecutable: false,
    signDlls: false,
    target: [{ target: "dir", arch: ["x64"] }],
  },
};
const configPath = join(appDir, ".electron-builder.jack.json");
writeFileSync(configPath, JSON.stringify(buildConfig, null, 2) + "\n", "utf8");
try {
  runNode(join(appDir, "node_modules", "electron-builder", "out", "cli", "cli.js"), ["--win", "--publish", "never", "--config", configPath]);
} finally {
  rmSync(configPath, { force: true });
}
console.log(`[build] Jack Codex artifacts: ${output}`);
