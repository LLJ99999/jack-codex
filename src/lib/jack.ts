/** preload 暴露的 Jack Codex IPC 接口类型。 */
export type InstalledMap = Record<string, string | boolean>;
export type InstallResult = {
  ok: boolean;
  code: number;
  out: string;
  timedOut: boolean;
  installed: InstalledMap;
  error?: string;
};
export type RestartResult = { ok: boolean; code?: number; out?: string; error?: string };
export type Skill = { name: string; desc: string; enabled: boolean };
export type AppState = { installed: InstalledMap; autoInstall: boolean; version: string };
export type LogPayload = { label: string; text: string };
export type StatusPayload = { label: string; state: "running" | "idle" };
export type NotifyPayload = { level: "info" | "warn"; text: string };

export type JackApi = {
  state(): Promise<AppState>;
  install(targetId: "codex", promptFile: "jack-codex-v1.md"): Promise<InstallResult>;
  uninstall(targetId: "codex"): Promise<InstallResult>;
  restartCodex(): Promise<RestartResult>;
  listSkills(): Promise<Skill[]>;
  saveSkills(disabled: string[]): Promise<{ ok: boolean; error?: string }>;
  setAutoInstall(value: boolean): Promise<{ autoInstall: boolean }>;
  quit(): Promise<{ ok: boolean }>;
  win(action: "minimize" | "maximize" | "close"): Promise<{ ok: boolean }>;
  onLog(cb: (p: LogPayload) => void): () => void;
  onStatus(cb: (p: StatusPayload) => void): () => void;
  onNotify(cb: (p: NotifyPayload) => void): () => void;
};

declare global {
  interface Window {
    jack: JackApi;
  }
}

const previewSkills: Skill[] = [
  { name: "reverse-engineering", desc: "二进制结构、反编译与行为恢复", enabled: true },
  { name: "apk-reverse", desc: "Android APK 解包与动态分析", enabled: true },
  { name: "api-security", desc: "接口鉴权与安全边界验证", enabled: true },
  { name: "binary-diff", desc: "跨版本符号迁移与差分", enabled: true },
];

const previewApi: JackApi = {
  async state() { return { installed: { codex: "Jack Codex v1" }, autoInstall: false, version: "1.0.0" }; },
  async install() { return { ok: true, code: 0, out: "preview", timedOut: false, installed: { codex: "Jack Codex v1" } }; },
  async uninstall() { return { ok: true, code: 0, out: "preview", timedOut: false, installed: {} }; },
  async restartCodex() { return { ok: true }; },
  async listSkills() { return previewSkills; },
  async saveSkills() { return { ok: true }; },
  async setAutoInstall(autoInstall) { return { autoInstall }; },
  async quit() { return { ok: true }; },
  async win() { return { ok: true }; },
  onLog() { return () => undefined; },
  onStatus() { return () => undefined; },
  onNotify() { return () => undefined; },
};

export const jack: JackApi = window.jack || (import.meta.env.DEV ? previewApi : window.jack);
