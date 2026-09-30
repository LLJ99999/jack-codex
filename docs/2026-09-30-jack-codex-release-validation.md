# Jack Codex 1.0.0 发行验收

## 结论

通过。发行包仅面向 Codex，产品名为 **Jack Codex 工具**，包含一个提示词与一个 Skills 树。

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `release/Jack-Codex-Setup-1.0.0.exe` | 92,904,646 bytes | `0F08C8662D7988F4821516FE68DAD5E5B2FFEAA07821EDE64C734B9300C2CC07` |
| `release/Jack-Codex-Portable-1.0.0.exe` | 92,688,711 bytes | `D5CDCFCEA2CE61AB2DC45C4B992980E179305A797D240C19904FB42159D34BB7` |

当前未配置 Authenticode 证书，两个 EXE 的签名状态均为 `NotSigned`。

## 发行内容

- PE ProductName：`Jack Codex 工具`
- CompanyName：`Jack`
- FileVersion：`1.0.0`
- 唯一提示词：`jack-codex-v1.md`
- 唯一 Skills 树：`codex-skills/`
- 一级 Skills：63
- 非 Codex 安装器与遗留负载：0
- 旧品牌文本：0
- 用户要求删除的中转站条款文本：0

## 正式前端

- 苹果式极简浅色桌面壳与无边框窗口；
- 概览、Skills、使用指南、设置四个正式视图；
- 安装、重新安装、重启 Codex、运行日志完整保留；
- 概览页提供“卸载并恢复原配置”及二次确认；
- Skills 支持搜索、全部启用、全部停用、重新读取与保存；
- 真实 React 页面已完成 1440×900 视觉截图验收。

## 安装与卸载验收

已覆盖：

1. 安装、重复安装、卸载、重复卸载；
2. 保留无关 `config.toml`、`AGENTS.md` 与用户 Skill；
3. 同名提示词、同名用户 Skill 的备份与恢复；
4. 保留用户修改过的受管提示词与 Skill；
5. 保留安装后用户自行修改的 `model_instructions_file`；
6. 移除 Jack Skills 配置标记块；
7. 新建配置文件的完整回滚；
8. 中途失败的事务回滚；
9. 升级时退役 Skill 与用户碰撞目录恢复；
10. 固定安装时 `CODEX_HOME`，环境变量变化后仍卸载原目录；
11. 使用 `win-unpacked/resources` 中的真实发行资源完成安装/卸载冒烟。

## 命令结果

- `npm test`：通过
- `npm run build`：通过
- `npm run dist`：通过
- Electron / Node / PowerShell 语法检查：通过
- `git diff --check`：通过
- 安装器安全复审：通过，无发行阻断项
