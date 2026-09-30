import type { StatusLevel } from "../App";
import { cx } from "../lib/cx";

type Props = {
  version: string;
  status: string;
  level: StatusLevel;
  autoInstall: boolean;
  onToggleAuto: () => void;
  onQuit: () => void;
};

export function ProfilePage({ version, status, level, autoInstall, onToggleAuto, onQuit }: Props) {
  return (
    <>
      <div className="jack-section-heading"><div><h1>设置</h1><p>管理启动行为和应用状态。</p></div><p>Jack Codex 只操作本机 CODEX_HOME，不连接账号服务。</p></div>
      <section className="jack-settings-panel">
        <div className="jack-setting-row"><div><h3>运行状态</h3><p>最近一次安装、卸载或保存操作的结果。</p></div><span className={cx("jack-status-badge", level)}>{status}</span></div>
        <div className="jack-setting-row"><div><h3>应用版本</h3><p>当前安装的 Jack Codex 桌面工具版本。</p></div><span className="jack-status-badge">{version ? `v${version}` : "—"}</span></div>
        <button type="button" className="jack-setting-row jack-setting-button" onClick={onToggleAuto}><div><h3>启动时自动修复 Jack 配置</h3><p>仅在已安装状态下重新应用同一份 Jack 指令。</p></div><span className={cx("jack-toggle", autoInstall && "on")}><i /></span></button>
      </section>
      <div className="jack-settings-foot"><button type="button" className="jack-button secondary" onClick={onQuit}>退出工具</button></div>
    </>
  );
}
