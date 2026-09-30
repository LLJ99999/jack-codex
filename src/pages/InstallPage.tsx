import { useState } from "react";

import type { StatusLevel } from "../App";
import { IconArchiveRestore, IconCheck, IconListChecks, IconRefresh, IconShield } from "../components/icons";
import type { Target } from "../data/targets";
import { cx } from "../lib/cx";

type Props = {
  target: Target;
  installed?: string | boolean;
  busy: boolean;
  status: string;
  level: StatusLevel;
  logText: string;
  onInstall: (file: string, label?: string) => void;
  onUninstall: () => void;
  onRestart: () => void;
};

export function InstallPage({ target, installed, busy, status, level, logText, onInstall, onUninstall, onRestart }: Props) {
  const [uninstallOpen, setUninstallOpen] = useState(false);
  const selected = target.versions[0];
  const isInstalled = Boolean(installed);
  const score = level === "err" ? 40 : isInstalled ? 100 : 84;

  const confirmUninstall = () => {
    setUninstallOpen(false);
    onUninstall();
  };

  return (
    <>
      <div className="jack-page-heading">
        <div><h1>概览</h1><p>管理 Jack 配置与 Codex Skills。</p></div>
        <div className="jack-path"><span>当前配置</span><b>CODEX_HOME</b></div>
      </div>

      <section className="jack-hero-card">
        <div className="jack-hero-main">
          <div>
            <div className={cx("jack-kicker", level === "err" && "error")}><i />{busy ? "正在执行" : level === "err" ? "需要处理" : isInstalled ? "配置已安装" : "环境已就绪"}</div>
            <h2>{isInstalled ? "Jack Codex 正在运行" : "Jack Codex 可以安装"}</h2>
            <p>{target.desc}</p>
          </div>
          <div className="jack-score"><span>配置完整度</span><strong>{score}<small>%</small></strong><em>{isInstalled ? "提示词与 Skills 已部署" : "所有必要文件均可访问"}</em></div>
        </div>
        <div className="jack-hero-actions">
          <div className="jack-safe-note"><i><IconShield size={13} /></i><span>安装前自动创建完整快照</span></div>
          <div className="jack-action-group">
            {isInstalled && <button type="button" className="jack-button secondary" disabled={busy} onClick={onRestart}>重启 Codex</button>}
            <button type="button" className="jack-button primary" disabled={busy || !selected} onClick={() => selected && onInstall(selected.file, selected.name)}>{busy ? "执行中…" : isInstalled ? "重新安装" : "安装 Jack Codex"}</button>
          </div>
        </div>
      </section>

      <div className="jack-feature-grid">
        <article className="jack-feature-card"><div><IconListChecks size={16} /></div><span>已就绪</span><h3>63 个 Skills</h3><p>统一索引，可在 Skills 页面选择启用。</p></article>
        <article className="jack-feature-card"><div><IconCheck size={16} /></div><span>安全</span><h3>事务化安装</h3><p>任一步失败都会自动恢复原始状态。</p></article>
        <article className="jack-feature-card"><div><IconArchiveRestore size={16} /></div><span>可恢复</span><h3>精确卸载</h3><p>只处理 Jack 状态清单记录的文件。</p></article>
      </div>

      <section className="jack-activity-card">
        <div className="jack-card-head"><strong>运行状态</strong><span>{level === "busy" ? "实时更新" : "最近结果"}</span></div>
        <div className={cx("jack-status-line", level)}><i />{status}</div>
        {logText && <pre className="jack-log">{logText}</pre>}
      </section>

      <section className="jack-restore-card">
        <div><i><IconRefresh size={17} /></i><span><strong>恢复原始配置</strong><small>卸载 Jack 提示词与受管 Skills，并恢复安装前的配置和同名文件。</small></span></div>
        <button type="button" className="jack-button danger" disabled={busy || !isInstalled} onClick={() => setUninstallOpen(true)}>卸载并恢复原配置</button>
      </section>

      {uninstallOpen && <div className="jack-overlay"><section className="jack-dialog compact" role="alertdialog" aria-modal="true" aria-labelledby="uninstall-title"><div className="jack-dialog-symbol danger"><IconArchiveRestore size={20} /></div><h2 id="uninstall-title">卸载 Jack 配置？</h2><p>将按安装状态清单恢复原始配置。安装后由你修改过的受管文件会保留副本，不会直接覆盖。</p><div className="jack-dialog-actions"><button type="button" className="jack-button danger solid" onClick={confirmUninstall}>卸载并恢复</button><button type="button" className="jack-button secondary" onClick={() => setUninstallOpen(false)}>取消</button></div></section></div>}
    </>
  );
}
