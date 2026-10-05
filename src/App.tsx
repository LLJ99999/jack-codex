import { useCallback, useEffect, useRef, useState } from "react";

import brandMark from "./assets/brand.png";
import {
  IconBookOpen,
  IconCheck,
  IconCircleAlert,
  IconListChecks,
  IconSettings,
  IconSparkles,
} from "./components/icons";
import { APP_NAME, APP_VERSION, DISCLAIMER_TEXT, DISCLAIMER_TITLE, PROMPT_FILE, TARGETS } from "./data/targets";
import { jack, type InstalledMap, type Skill } from "./lib/jack";
import { cx } from "./lib/cx";
import { InstallPage } from "./pages/InstallPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SkillsPage } from "./pages/SkillsPage";
import { TutorialPage } from "./pages/TutorialPage";

type ViewId = "codex" | "skills" | "tutorial" | "profile";
export type StatusLevel = "idle" | "busy" | "ok" | "err";

const VIEW_LABELS: Record<ViewId, string> = {
  codex: "概览",
  skills: "Skills",
  tutorial: "使用指南",
  profile: "设置",
};

export function App() {
  const [consent, setConsent] = useState(import.meta.env.DEV);
  const [view, setView] = useState<ViewId>("codex");
  const [installed, setInstalled] = useState<InstalledMap>({});
  const [autoInstall, setAutoInstallState] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("就绪");
  const [level, setLevel] = useState<StatusLevel>("idle");
  const [logText, setLogText] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [toastLevel, setToastLevel] = useState<"success" | "error">("success");
  const autoRan = useRef(false);

  useEffect(() => { document.title = APP_NAME; }, []);
  useEffect(() => {
    jack.state().then((state) => {
      setInstalled(state.installed || {});
      setAutoInstallState(Boolean(state.autoInstall));
    });
    jack.listSkills().then(setSkills);
  }, []);
  useEffect(() => {
    const offLog = jack.onLog((payload) => setLogText((previous) => (previous + payload.text).slice(-20000)));
    const offStatus = jack.onStatus((payload) => {
      setBusy(payload.state === "running");
      setStatus(payload.label);
      setLevel(payload.state === "running" ? "busy" : "idle");
    });
    const offNotify = jack.onNotify((payload) => setToast(payload.text));
    return () => { offLog(); offStatus(); offNotify(); };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const reloadSkills = useCallback(() => { jack.listSkills().then(setSkills); }, []);
  const runInstall = useCallback(async (_file: string, label?: string) => {
    const shown = label || "Jack Codex v1";
    setLogText(""); setStatus(`正在安装 ${shown} …`); setLevel("busy"); setBusy(true);
    const result = await jack.install("codex", PROMPT_FILE);
    setInstalled(result.installed || {});
    if (result.ok) { setStatus(`${shown} 安装成功 · 重启 Codex 后生效`); setLevel("ok"); }
    else if (result.timedOut) { setStatus("安装超时，进程已终止"); setLevel("err"); }
    else {
      const detail = (result.error || result.out || `退出码 ${result.code}`).trim().split(/\r?\n/).filter(Boolean).slice(-3).join(" / ");
      setStatus(`安装失败：${detail}`);
      setLevel("err");
      if (result.out) setLogText(result.out);
    }
    setBusy(false); reloadSkills();
  }, [reloadSkills]);
  const runUninstall = useCallback(async () => {
    setLogText(""); setStatus("正在卸载 Jack 配置 …"); setLevel("busy"); setBusy(true);
    const result = await jack.uninstall("codex");
    setInstalled(result.installed || {});
    setStatus(result.ok ? "Jack 配置已卸载，原配置已恢复" : `卸载失败：${result.error || `退出码 ${result.code}`}`);
    setLevel(result.ok ? "ok" : "err"); setBusy(false); reloadSkills();
  }, [reloadSkills]);
  const runRestart = useCallback(async () => {
    setStatus("正在重启 Codex …"); setLevel("busy");
    const result = await jack.restartCodex();
    setStatus(result.ok ? "Codex 已重启" : `重启失败：${result.error || "未知错误"}`);
    setLevel(result.ok ? "ok" : "err");
  }, []);
  const toggleAuto = useCallback(async () => {
    const next = !autoInstall;
    setAutoInstallState(next);
    await jack.setAutoInstall(next);
  }, [autoInstall]);
  const saveSkills = useCallback(async (disabled: string[]) => {
    const result = await jack.saveSkills(disabled);
    setToastLevel(result.ok ? "success" : "error");
    setToast(result.ok ? "Skills 配置已保存 · 重启 Codex 生效" : `保存失败：${result.error || "无法写入配置"}`);
    setStatus(result.ok ? "Skills 配置已保存" : "Skills 配置保存失败");
    setLevel(result.ok ? "ok" : "err");
    if (result.ok) reloadSkills();
  }, [reloadSkills]);

  useEffect(() => {
    if (!consent || !autoInstall || autoRan.current || !installed.codex) return;
    autoRan.current = true;
    runInstall(PROMPT_FILE, "Jack Codex v1");
  }, [consent, autoInstall, installed.codex, runInstall]);

  const navItem = (id: ViewId, Icon: typeof IconSparkles, count?: number) => (
    <button type="button" className={cx("jack-nav-item", view === id && "active")} onClick={() => setView(id)}>
      <Icon size={17} /><span>{VIEW_LABELS[id]}</span>{typeof count === "number" && <i>{count}</i>}
    </button>
  );

  return (
    <div className="jack-shell">
      <header className="jack-titlebar">
        <div className="jack-window-lights">
          <button type="button" aria-label="关闭窗口" onClick={() => jack.win("close")} />
          <button type="button" aria-label="最小化窗口" onClick={() => jack.win("minimize")} />
          <button type="button" aria-label="最大化或还原窗口" onClick={() => jack.win("maximize")} />
        </div>
        <strong>{APP_NAME}</strong>
      </header>
      <div className="jack-layout">
        <aside className="jack-sidebar">
          <div className="jack-identity">
            <img src={brandMark} alt="" aria-hidden="true" draggable={false} />
            <span><b>Jack Codex</b><small>版本 {APP_VERSION}</small></span>
          </div>
          <div className="jack-nav-label">工具</div>
          <nav className="jack-nav">
            {navItem("codex", IconSparkles)}
            {navItem("skills", IconListChecks, skills.length)}
            {navItem("tutorial", IconBookOpen)}
            {navItem("profile", IconSettings)}
          </nav>
          <div className="jack-sidebar-spacer" />
          <div className="jack-connection"><span><i />Codex 已连接</span><small>本地配置 · 可安全恢复</small></div>
          <div className="jack-version">JACK DESKTOP · {APP_VERSION}</div>
        </aside>
        <main className="jack-content">
          {view === "codex" && <InstallPage target={TARGETS[0]} installed={installed.codex} busy={busy} status={status} level={level} logText={logText} onInstall={runInstall} onUninstall={runUninstall} onRestart={runRestart} />}
          {view === "skills" && <SkillsPage skills={skills} onSave={saveSkills} onReload={reloadSkills} />}
          {view === "tutorial" && <TutorialPage />}
          {view === "profile" && <ProfilePage version={APP_VERSION} status={status} level={level} autoInstall={autoInstall} onToggleAuto={toggleAuto} onQuit={() => jack.quit()} />}
        </main>
      </div>
      {toast && <button type="button" className={cx("jack-toast", toastLevel === "error" && "error")} onClick={() => setToast(null)}>{toastLevel === "error" ? <IconCircleAlert size={15} /> : <IconCheck size={15} />}<span>{toast}</span></button>}
      {!consent && <div className="jack-overlay"><section className="jack-dialog" role="dialog" aria-modal="true" aria-labelledby="consent-title"><img src={brandMark} alt="" aria-hidden="true" /><h2 id="consent-title">{DISCLAIMER_TITLE}</h2><p>{DISCLAIMER_TEXT}</p><div className="jack-dialog-actions"><button type="button" className="jack-button primary" onClick={() => setConsent(true)}>继续</button><button type="button" className="jack-button secondary" onClick={() => jack.quit()}>退出</button></div></section></div>}
    </div>
  );
}
