"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { fileURLToPath } = require("node:url");

const APP_NAME = "Jack Codex 工具";
const PROMPT_NAME = "jack-codex-v1.md";
const INSTALL_TIMEOUT_MS = 300000;
const UNINSTALL_TIMEOUT_MS = 120000;
const SKILLS_BEGIN = "# JACK-CODEX-SKILLS BEGIN";
const SKILLS_END = "# JACK-CODEX-SKILLS END";

let win = null;
let quitting = false;
let activePowerShell = null;
let activeTimer = null;

function resourceRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, "..");
}

function installerPath() {
  return path.join(resourceRoot(), "install.ps1");
}

function promptPath() {
  return path.join(resourceRoot(), PROMPT_NAME);
}

function packagedSkillsPath() {
  return path.join(resourceRoot(), "codex-skills");
}

function distIndexPath() {
  return path.resolve(__dirname, "..", "dist", "index.html");
}

function codexHome() {
  const configured = process.env.CODEX_HOME;
  return path.resolve(configured && configured.trim() ? configured : path.join(os.homedir(), ".codex"));
}

function desktopStatePath() {
  return path.join(app.getPath("userData"), "jack-desktop-state.json");
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonAtomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(value, null, 2) + "\n", "utf8");
  fs.renameSync(temp, file);
}

function normalizeSkillNames(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((name) =>
    typeof name === "string" &&
    name.length > 0 &&
    name.length <= 160 &&
    path.basename(name) === name &&
    name !== "." &&
    name !== "..",
  );
}

function loadState() {
  const raw = readJson(desktopStatePath(), {});
  return {
    installed: raw.installed === true,
    installedCodexHome: typeof raw.installedCodexHome === "string" && path.isAbsolute(raw.installedCodexHome) ? path.resolve(raw.installedCodexHome) : null,
    autoInstall: raw.autoInstall === true,
    manifest: {
      skills: normalizeSkillNames(raw.manifest && raw.manifest.skills),
    },
  };
}

function saveState(patch) {
  const current = loadState();
  const next = {
    ...current,
    ...patch,
    manifest: {
      ...current.manifest,
      ...(patch.manifest || {}),
    },
  };
  next.manifest.skills = normalizeSkillNames(next.manifest.skills);
  writeJsonAtomic(desktopStatePath(), next);
  return next;
}

function installerStatePath(homeValue) {
  return path.join(homeValue || loadState().installedCodexHome || codexHome(), ".jack-codex", "install-state.json");
}

function publicState() {
  const state = loadState();
  const installed = state.installed && fs.existsSync(installerStatePath(state.installedCodexHome));
  return {
    installed: installed ? { codex: "Jack Codex v1" } : {},
    autoInstall: state.autoInstall,
    version: app.getVersion(),
  };
}

function sendEvent(name, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(`jack:${name}`, payload);
}

function isTrustedSender(event) {
  try {
    const frameUrl = event.senderFrame && event.senderFrame.url;
    if (!frameUrl || !frameUrl.startsWith("file:")) return false;
    return path.resolve(fileURLToPath(frameUrl)) === distIndexPath();
  } catch {
    return false;
  }
}

function handle(channel, handler) {
  ipcMain.handle(`jack:${channel}`, (event, ...args) => {
    if (!isTrustedSender(event)) throw new Error("Untrusted IPC sender");
    return handler(...args);
  });
}

function requireResources() {
  const required = [installerPath(), promptPath(), packagedSkillsPath()];
  const missing = required.filter((entry) => !fs.existsSync(entry));
  if (missing.length) throw new Error(`缺少随包资源：${missing.map(path.basename).join(", ")}`);
}

function installerArgs(action, homeValue) {
  if (action !== "Install" && action !== "Uninstall") throw new Error("Invalid installer action");
  requireResources();
  const args = [
    "-NoProfile",
    "-NonInteractive",
    "-File", installerPath(),
    "-Action", action,
    "-PromptFile", promptPath(),
    "-SkillsSource", packagedSkillsPath(),
  ];
  if (homeValue) args.push("-CodexHome", homeValue);
  return args;
}

function stopActivePowerShell() {
  if (activeTimer) clearTimeout(activeTimer);
  activeTimer = null;
  if (activePowerShell) {
    try { activePowerShell.kill(); } catch { /* process already exited */ }
  }
  activePowerShell = null;
}

function runPowerShell(args, label, timeoutMs) {
  return new Promise((resolve) => {
    if (activePowerShell) {
      resolve({ ok: false, code: -1, out: "", timedOut: false, error: "已有任务正在运行" });
      return;
    }

    let output = "";
    let timedOut = false;
    let settled = false;
    sendEvent("status", { label, state: "running" });

    const child = spawn("powershell.exe", args, {
      cwd: resourceRoot(),
      windowsHide: true,
    });
    activePowerShell = child;

    const append = (buffer) => {
      const text = buffer.toString("utf8");
      output = (output + text).slice(-60000);
      sendEvent("log", { label, text });
    };
    child.stdout.on("data", append);
    child.stderr.on("data", append);

    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (activeTimer) clearTimeout(activeTimer);
      activeTimer = null;
      if (activePowerShell === child) activePowerShell = null;
      sendEvent("status", { label, state: "idle" });
      resolve(result);
    };

    activeTimer = setTimeout(() => {
      timedOut = true;
      sendEvent("log", { label, text: "\n[超时] 已终止安装任务\n" });
      try { child.kill(); } catch { /* process already exited */ }
    }, timeoutMs);

    child.once("error", (error) => finish({
      ok: false,
      code: -1,
      out: output,
      timedOut,
      error: String(error && error.message || error),
    }));
    child.once("close", (code) => finish({
      ok: !timedOut && code === 0,
      code: code == null ? -1 : code,
      out: output,
      timedOut,
      ...(timedOut ? { error: "操作超时" } : {}),
    }));
  });
}

function bundledSkillNames() {
  try {
    return fs.readdirSync(packagedSkillsPath(), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(packagedSkillsPath(), entry.name, "SKILL.md")))
      .map((entry) => entry.name);
  } catch {
    return [];
  }
}

function installerManifestSkillNames() {
  const manifest = readJson(installerStatePath(), {});
  if (!Array.isArray(manifest.skills)) return [];
  return normalizeSkillNames(manifest.skills.map((item) => item && item.name));
}

function jackSkillNames() {
  return new Set([
    ...bundledSkillNames(),
    ...loadState().manifest.skills,
    ...installerManifestSkillNames(),
  ]);
}

function skillsDir() {
  return path.join(codexHome(), "skills");
}

function configPath() {
  return path.join(codexHome(), "config.toml");
}

function markedSkillsBlock(text) {
  const begin = text.indexOf(SKILLS_BEGIN);
  const end = text.indexOf(SKILLS_END);
  if (begin === -1 && end === -1) return null;
  if (begin === -1 || end === -1 || end < begin || text.indexOf(SKILLS_BEGIN, begin + 1) !== -1 || text.indexOf(SKILLS_END, end + 1) !== -1) {
    throw new Error("config.toml 中的 JACK-CODEX-SKILLS 标记块不完整");
  }
  return { begin, end: end + SKILLS_END.length, text: text.slice(begin, end + SKILLS_END.length) };
}

function disabledJackSkills(text) {
  const block = markedSkillsBlock(text);
  if (!block) return new Set();
  const disabled = new Set();
  const sections = block.text.split(/^\s*\[\[skills\.config\]\]\s*$/m).slice(1);
  for (const section of sections) {
    const pathMatch = section.match(/^\s*path\s*=\s*"([^"]+)"/m);
    const enabledMatch = section.match(/^\s*enabled\s*=\s*(true|false)\s*$/m);
    if (!pathMatch || !enabledMatch || enabledMatch[1] !== "false") continue;
    const normalized = pathMatch[1].replace(/\\/g, "/");
    const parts = normalized.split("/").filter(Boolean);
    if (parts.at(-1) !== "SKILL.md") continue;
    const name = parts.at(-2);
    if (name) disabled.add(name);
  }
  return disabled;
}

function skillDescription(skillFile) {
  try {
    const head = fs.readFileSync(skillFile, "utf8").slice(0, 2000);
    const match = head.match(/^description:\s*["']?(.+?)["']?\s*$/m);
    return match ? match[1].trim().slice(0, 120) : "";
  } catch {
    return "";
  }
}

function listSkills() {
  const allowed = jackSkillNames();
  let config = "";
  try { config = fs.readFileSync(configPath(), "utf8"); } catch { /* no config yet */ }
  const disabled = disabledJackSkills(config);
  const root = skillsDir();
  try {
    return fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && allowed.has(entry.name))
      .map((entry) => ({ name: entry.name, file: path.join(root, entry.name, "SKILL.md") }))
      .filter((entry) => fs.existsSync(entry.file))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((entry) => ({
        name: entry.name,
        desc: skillDescription(entry.file),
        enabled: !disabled.has(entry.name),
      }));
  } catch {
    return [];
  }
}

function tomlString(value) {
  return value.replace(/\\/g, "/").replace(/"/g, '\\"');
}

function saveSkills(disabledValue) {
  try {
    const requested = normalizeSkillNames(disabledValue);
    if (!Array.isArray(disabledValue) || requested.length !== disabledValue.length) {
      return { ok: false, error: "Skills 列表格式无效" };
    }
    const available = new Set(listSkills().map((skill) => skill.name));
    if (requested.some((name) => !available.has(name))) {
      return { ok: false, error: "包含非 Jack 管理的 skill" };
    }

    const file = configPath();
    let current = "";
    try { current = fs.readFileSync(file, "utf8"); } catch (error) {
      if (error && error.code !== "ENOENT") throw error;
    }

    const entries = [...new Set(requested)].sort().map((name) => {
      const skillFile = tomlString(path.join(skillsDir(), name, "SKILL.md"));
      return `[[skills.config]]\npath = "${skillFile}"\nenabled = false`;
    });
    const replacement = [SKILLS_BEGIN, ...entries, SKILLS_END].join("\n");
    const existing = markedSkillsBlock(current);
    let next;
    if (existing) {
      next = current.slice(0, existing.begin) + replacement + current.slice(existing.end);
    } else {
      const separator = current.length === 0 ? "" : current.endsWith("\n") ? "\n" : "\n\n";
      next = current + separator + replacement + "\n";
    }

    fs.mkdirSync(path.dirname(file), { recursive: true });
    const temp = `${file}.${process.pid}.jack.tmp`;
    fs.writeFileSync(temp, next, "utf8");
    fs.renameSync(temp, file);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: String(error && error.message || error) };
  }
}

async function install() {
  let result;
  const installHome = codexHome();
  try {
    result = await runPowerShell(installerArgs("Install", installHome), "安装 Jack Codex v1", INSTALL_TIMEOUT_MS);
  } catch (error) {
    result = { ok: false, code: -1, out: "", timedOut: false, error: String(error && error.message || error) };
  }
  if (result.ok) {
    saveState({ installed: true, installedCodexHome: installHome, manifest: { skills: bundledSkillNames() } });
    sendEvent("notify", { level: "info", text: "Jack Codex v1 安装完成" });
  }
  return { ...result, installed: publicState().installed };
}

async function uninstall() {
  let result;
  const uninstallHome = loadState().installedCodexHome || codexHome();
  try {
    result = await runPowerShell(installerArgs("Uninstall", uninstallHome), "卸载 Jack Codex v1", UNINSTALL_TIMEOUT_MS);
  } catch (error) {
    result = { ok: false, code: -1, out: "", timedOut: false, error: String(error && error.message || error) };
  }
  if (result.ok) {
    saveState({ installed: false, installedCodexHome: null, manifest: { skills: [] } });
    sendEvent("notify", { level: "info", text: "Jack Codex v1 已卸载" });
  }
  return { ...result, installed: publicState().installed };
}

function restartCodex() {
  const label = "重启 Codex";
  const command = [
    "$ErrorActionPreference = 'Stop'",
    "$entry = Get-StartApps | Where-Object { $_.Name -eq 'Codex' -or $_.AppID -like 'OpenAI.Codex*' } | Select-Object -First 1",
    "if (-not $entry) { throw '未找到 Codex 开始菜单入口' }",
    "$processes = @(Get-Process -Name 'ChatGPT' -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*OpenAI.Codex*' })",
    "foreach ($process in $processes) {",
    "  if (-not $process.CloseMainWindow()) { throw ('Codex 窗口不接受温和关闭，PID=' + $process.Id) }",
    "  if (-not $process.WaitForExit(5000)) { throw ('Codex 未在 5 秒内退出，PID=' + $process.Id) }",
    "}",
    "Start-Process ('shell:AppsFolder\\' + $entry.AppID)",
    "Write-Output ('launched:' + $entry.AppID)",
  ].join("; ");
  return runPowerShell(
    ["-NoProfile", "-NonInteractive", "-Command", command],
    label,
    30000,
  ).then((result) => ({
    ok: result.ok && /(^|\r?\n)launched:/m.test(result.out),
    code: result.code,
    out: result.out.trim(),
    ...(!result.ok ? { error: result.error || result.out.trim() || "Codex 重启失败" } : {}),
  }));
}

function registerIpc() {
  handle("state", () => publicState());
  handle("install", () => install());
  handle("uninstall", () => uninstall());
  handle("restartCodex", () => restartCodex());
  handle("listSkills", () => listSkills());
  handle("saveSkills", (disabled) => saveSkills(disabled));
  handle("setAutoInstall", (value) => {
    const next = saveState({ autoInstall: value === true });
    return { autoInstall: next.autoInstall };
  });
  handle("quit", () => {
    app.quit();
    return { ok: true };
  });
  handle("win", (action) => {
    if (!win || win.isDestroyed()) return { ok: false };
    if (action === "minimize") win.minimize();
    else if (action === "maximize") win.isMaximized() ? win.unmaximize() : win.maximize();
    else if (action === "close") win.close();
    else return { ok: false };
    return { ok: true };
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 940,
    minHeight: 620,
    show: false,
    title: APP_NAME,
    backgroundColor: "#f5f5f7",
    frame: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event) => event.preventDefault());
  win.webContents.on("will-attach-webview", (event) => event.preventDefault());

  const show = () => {
    if (win && !win.isDestroyed()) win.show();
  };
  win.once("ready-to-show", show);
  win.webContents.once("did-finish-load", show);
  win.loadFile(distIndexPath());

  win.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.on("closed", () => { win = null; });
}

function showWindow() {
  if (!win || win.isDestroyed()) {
    createWindow();
    return;
  }
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", showWindow);
  app.whenReady().then(() => {
    registerIpc();
    createWindow();
  });
  app.on("activate", showWindow);
  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
  app.on("before-quit", () => {
    quitting = true;
    stopActivePowerShell();
  });
}
