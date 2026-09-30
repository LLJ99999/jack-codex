import { useEffect, useMemo, useState } from "react";

import { IconRefresh, IconSearch } from "../components/icons";
import { cx } from "../lib/cx";
import type { Skill } from "../lib/jack";

type Props = {
  skills: Skill[];
  onSave: (disabled: string[]) => void;
  onReload: () => void;
};

export function SkillsPage({ skills, onSave, onReload }: Props) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");

  useEffect(() => {
    const next: Record<string, boolean> = {};
    for (const skill of skills) next[skill.name] = skill.enabled;
    setEnabled(next);
  }, [skills]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return skills;
    return skills.filter((skill) => `${skill.name} ${skill.desc}`.toLowerCase().includes(needle));
  }, [query, skills]);
  const total = skills.length;
  const onCount = skills.filter((skill) => enabled[skill.name]).length;
  const toggle = (name: string) => setEnabled((previous) => ({ ...previous, [name]: !previous[name] }));
  const setAll = (value: boolean) => setEnabled(Object.fromEntries(skills.map((skill) => [skill.name, value])));
  const save = () => onSave(skills.filter((skill) => !enabled[skill.name]).map((skill) => skill.name));

  return (
    <>
      <div className="jack-section-heading"><div><h1>Skills</h1><p>控制 Jack 安装的技能，不影响你的其他内容。</p></div><p>共 {total} 个 · 已启用 {onCount} · 已停用 {total - onCount}</p></div>
      <div className="jack-skills-toolbar">
        <label className="jack-search-wrap"><IconSearch size={15} /><input className="jack-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Skills" /></label>
        <div className="jack-skills-actions"><button type="button" className="jack-button secondary" onClick={() => setAll(true)}>全部启用</button><button type="button" className="jack-button secondary" onClick={() => setAll(false)}>全部停用</button><button type="button" className="jack-button secondary" onClick={onReload}><IconRefresh size={13} />重新读取</button></div>
      </div>
      <div className="jack-skill-panel">
        {total === 0 ? <div className="jack-empty">尚未发现 Jack 管理的 Skills。安装 Jack Codex 后再回来查看。</div> : visible.length === 0 ? <div className="jack-empty">没有匹配“{query}”的 Skill。</div> : visible.map((skill) => (
          <button key={skill.name} type="button" className="jack-skill-row" onClick={() => toggle(skill.name)} aria-pressed={Boolean(enabled[skill.name])}>
            <i className="jack-skill-mark">{skill.name.slice(0, 1).toUpperCase()}</i><strong>{skill.name}</strong><span>{skill.desc}</span><span className={cx("jack-toggle", enabled[skill.name] && "on")}><i /></span>
          </button>
        ))}
      </div>
      <div className="jack-savebar"><span>保存后需重启 Codex 才会生效。</span><button type="button" className="jack-button primary" onClick={save}>保存更改</button></div>
    </>
  );
}
