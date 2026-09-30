import { IconInfo } from "../components/icons";

const STEPS = [
  ["关闭 Codex", "避免安装时有其他进程同时写入配置，保证快照内容完整。"],
  ["安装 Jack Codex", "工具会先保存配置与碰撞文件，再写入提示词和受管 Skills。"],
  ["重启 Codex", "让新的提示词与 Skills 索引在新会话中生效。"],
  ["发送“Jack”", "在新会话中确认 Jack 工作模式已经正确加载。"],
] as const;

export function TutorialPage() {
  return (
    <>
      <div className="jack-section-heading"><div><h1>使用指南</h1><p>四个步骤完成部署与验证。</p></div><p>所有写入都限定在 CODEX_HOME，并在安装前创建恢复快照。</p></div>
      <div className="jack-guide-grid">{STEPS.map(([title, description], index) => <article className="jack-guide-card" key={title}><i>{index + 1}</i><div><h3>{title}</h3><p>{description}</p></div></article>)}</div>
      <div className="jack-guide-note"><IconInfo size={16} /><span>需要恢复时，回到“概览”底部点击“卸载并恢复原配置”。工具会依据安装状态清单精确回滚，并保留安装后由你修改过的受管文件副本。</span></div>
    </>
  );
}
