import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];
const textExtensions = new Set([
  ".cjs", ".css", ".html", ".js", ".json", ".jsx", ".md", ".mjs", ".ps1",
  ".ts", ".tsx", ".txt", ".yaml", ".yml",
]);

function rel(file) {
  return relative(root, file).split(sep).join("/");
}

function isAllowedHistoricalFile(file) {
  const path = rel(file).toLowerCase();
  return path === "license" ||
    path.startsWith("docs/") ||
    /(^|\/)(migration|migrations|compat|compatibility|legacy)(\/|[-_.])/.test(path) ||
    /(^|\/)[^/]*(migration|migrate|compat|legacy)[^/]*$/.test(path);
}

function textFiles(entry) {
  if (!existsSync(entry)) return [];
  const info = statSync(entry);
  if (info.isFile()) return textExtensions.has(extname(entry).toLowerCase()) ? [entry] : [];
  const files = [];
  for (const child of readdirSync(entry, { withFileTypes: true })) {
    if ([".git", "dist", "node_modules", "release", "tests"].includes(child.name)) continue;
    files.push(...textFiles(join(entry, child.name)));
  }
  return files;
}

function check(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
    console.error(`not ok - ${name}\n  ${error.message}`);
  }
}

const packagePath = join(root, "package.json");
const pkg = JSON.parse(readFileSync(packagePath, "utf8"));
const resources = Array.isArray(pkg.build?.extraResources) ? pkg.build.extraResources : [];
const resourcePaths = resources.flatMap((item) => {
  if (typeof item === "string") return [item];
  return [item?.from, item?.to].filter((value) => typeof value === "string");
});

const sourceEntries = [
  "src", "electron", "scripts", "build", "install.ps1", "portable-uninstall.ps1",
  "index.html", "vite.config.ts", "variant.json", "package.json",
].map((entry) => join(root, entry));
const packagedEntries = resources
  .map((item) => typeof item === "string" ? item : item?.from)
  .filter((value) => typeof value === "string")
  .map((entry) => resolve(root, entry));
const scannedFiles = [...new Set([...sourceEntries, ...packagedEntries].flatMap(textFiles))];

check("package resources contain only the Codex installer and Codex payload", () => {
  const badInstaller = resourcePaths.filter((entry) =>
    /(^|\/)install-(?!codex(?:\.|-))[^/]+\.ps1$/i.test(entry.replaceAll("\\", "/")),
  );
  assert.deepEqual(badInstaller, [], `non-Codex installers are packaged: ${badInstaller.join(", ")}`);

  const forbiddenResources = resourcePaths.filter((entry) =>
    /(^|[-_/])(zcode|cursor|claude|workbuddy|doubao|dsh)([-_/.]|$)/i.test(entry),
  );
  assert.deepEqual(forbiddenResources, [], `non-Codex platform resources are packaged: ${forbiddenResources.join(", ")}`);

  const promptResources = resources
    .map((item) => typeof item === "string" ? item : item?.from)
    .filter((entry) => typeof entry === "string" && /\.md$/i.test(entry));
  assert.deepEqual(promptResources, ["jack-codex-v1.md"], "the release must package exactly jack-codex-v1.md");

  const skillResources = resources
    .map((item) => typeof item === "string" ? item : item?.from)
    .filter((entry) => typeof entry === "string" && /(^|[\\/])codex-skills/i.test(entry));
  assert.deepEqual(skillResources, ["codex-skills"], "the release must package exactly one codex-skills tree");
  assert(resourcePaths.includes("install.ps1"), "install.ps1 is missing from package resources");
});

check("product source has no non-Codex installer or platform dispatch", () => {
  const nonCodex = "zcode|cursor|claude|workbuddy|doubao|dsh";
  const dispatchPatterns = [
    new RegExp(`install-(?:${nonCodex})\\.ps1`, "gi"),
    new RegExp(`\\b(?:target|targetId|platform|id)\\s*[:=]\\s*["'](?:${nonCodex})["']`, "gi"),
    new RegExp(`\\bcase\\s+["'](?:${nonCodex})["']`, "gi"),
    new RegExp(`^\\s*["']?(?:${nonCodex})["']?\\s*:\\s*["']install`, "gim"),
    new RegExp(`\\b(?:${nonCodex})(?:Home|Dir|Path|Target|TargetId|Installer)\\b`, "gi"),
  ];
  const hits = [];
  for (const file of scannedFiles) {
    if (isAllowedHistoricalFile(file) || rel(file).startsWith("codex-skills/")) continue;
    const content = readFileSync(file, "utf8");
    const matches = dispatchPatterns.flatMap((pattern) => [...content.matchAll(pattern)].map((match) => match[0]));
    if (matches.length) hits.push(`${rel(file)}: ${[...new Set(matches)].join(", ")}`);
  }
  assert.deepEqual(hits, [], `non-Codex dispatch remains:\n${hits.join("\n")}`);
});

check("public product source contains no retired brands", () => {
  const retiredBrandPattern = new RegExp([
    "寒" + "霜",
    "小" + "寒",
    "HAN" + "SHUANG",
    "SHI" + "YI",
    "海" + "鸥",
    "Sea" + "gull",
    "富" + "江",
  ].join("|"), "giu");
  const hits = [];
  for (const file of scannedFiles) {
    if (isAllowedHistoricalFile(file)) continue;
    const content = readFileSync(file, "utf8");
    const matches = [...content.matchAll(retiredBrandPattern)].map((match) => match[0]);
    if (matches.length) hits.push(`${rel(file)}: ${[...new Set(matches)].join(", ")}`);
  }
  assert.deepEqual(hits, [], `retired branding remains outside the allowlist:\n${hits.join("\n")}`);
});

check("packaged text contains no unwanted relay clause", () => {
  const forbiddenParts = ["api." + "zxcbug.com", "中转站" + "保护", "属己方" + "资产"];
  const hits = [];
  for (const file of scannedFiles) {
    const content = readFileSync(file, "utf8");
    const matches = forbiddenParts.filter((part) => content.includes(part));
    if (matches.length) hits.push(`${rel(file)}: ${matches.join(", ")}`);
  }
  assert.deepEqual(hits, [], `unwanted relay clause remains:\n${hits.join("\n")}`);
});

check("the formal UI uses the approved minimal shell and restore action", () => {
  const appSource = readFileSync(join(root, "src", "App.tsx"), "utf8");
  const installSource = readFileSync(join(root, "src", "pages", "InstallPage.tsx"), "utf8");
  const styles = readFileSync(join(root, "src", "styles", "app.css"), "utf8");
  assert(appSource.includes("jack-shell"), "App.tsx is not using the approved jack-shell");
  assert(styles.includes(".jack-shell"), "app.css is missing the approved shell styles");
  assert(installSource.includes("卸载并恢复原配置"), "the formal install page has no clear restore action");
  for (const view of ["codex", "skills", "tutorial", "profile"]) {
    assert(appSource.includes(`\"${view}\"`), `formal UI is missing the ${view} view`);
  }
});

check("the UI exposes exactly one Codex target", () => {
  const targetPath = join(root, "src", "data", "targets.ts");
  assert(existsSync(targetPath), "src/data/targets.ts is missing");
  const source = readFileSync(targetPath, "utf8");
  const targetList = source.match(/export\s+const\s+TARGETS[\s\S]*?=\s*\[([\s\S]*?)\n\s*\];/);
  assert(targetList, "TARGETS array was not found");
  const ids = [...targetList[1].matchAll(/\bid\s*:\s*["']([^"']+)["']/g)].map((match) => match[1]);
  assert.deepEqual(ids, ["codex"], `expected only the codex target, found: ${ids.join(", ") || "none"}`);
});

if (failures.length) {
  console.error(`\n${failures.length} package boundary check(s) failed.`);
  process.exitCode = 1;
} else {
  console.log("\nAll package boundary checks passed.");
}
