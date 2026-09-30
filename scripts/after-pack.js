"use strict";

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function findRcedit() {
  const cacheRoot = path.join(process.env.LOCALAPPDATA || "", "electron-builder", "Cache", "winCodeSign");
  try {
    for (const directory of fs.readdirSync(cacheRoot)) {
      const candidate = path.join(cacheRoot, directory, "rcedit-x64.exe");
      if (fs.existsSync(candidate)) return candidate;
    }
  } catch { /* optional metadata step */ }
  return null;
}

exports.default = async function afterPack(context) {
  const appRoot = path.join(__dirname, "..");
  const productName = context.packager.appInfo.productName;
  const executable = path.join(context.appOutDir, productName + ".exe");
  const rcedit = findRcedit();
  if (rcedit && fs.existsSync(executable)) {
    const args = [
      executable,
      "--set-version-string", "ProductName", productName,
      "--set-version-string", "FileDescription", "Jack Codex desktop configuration tool",
      "--set-version-string", "CompanyName", "Jack",
      "--set-file-version", context.packager.appInfo.version,
      "--set-product-version", context.packager.appInfo.version,
    ];
    const icon = path.join(appRoot, "build", "icon.ico");
    if (fs.existsSync(icon)) args.push("--set-icon", icon);
    try { execFileSync(rcedit, args, { stdio: "inherit" }); }
    catch (error) { console.warn("[after-pack] metadata update skipped:", error.message); }
  }
  for (const name of ["portable-uninstall.ps1", "卸载-便携版.bat"]) {
    const source = path.join(appRoot, name);
    if (fs.existsSync(source)) fs.copyFileSync(source, path.join(context.appOutDir, name));
  }
};
