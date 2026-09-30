# Jack Codex Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将原多平台寒霜工具重构为仅面向 Codex 的 Jack 品牌 Windows 桌面包，并保证安装、升级、卸载不会破坏用户自有配置或 Skills。

**Architecture:** 保留 Electron/Vite/React UI，但把目标模型收敛为单一 Codex。主进程只允许调用一个参数白名单化的 PowerShell 安装器；安装器仅在解析后的 `CODEX_HOME` 中写入精确文件，使用状态清单、哈希备份和 marker 完成事务式回滚。发行包只携带一个 Jack 提示词和一套审核后的 Codex Skills。

**Tech Stack:** Electron 33、React 19、TypeScript、Vite 5、PowerShell 5.1+、electron-builder、Node.js 测试脚本。

---

### Task 1: 建立回归测试和发行边界

**Files:**
- Create: `tests/validate-package.mjs`
- Create: `tests/test-installer.ps1`
- Modify: `package.json`

**Steps:**
1. 编写静态测试，断言 UI/主进程/打包资源不包含非 Codex 安装器和旧品牌。
2. 编写临时 `CODEX_HOME` 安装→升级→卸载测试，预置用户 `config.toml`、`AGENTS.md` 和自有 Skill。
3. 在 `package.json` 增加 `test`、`test:static`、`test:installer`。
4. 运行测试并确认它们在原代码上失败。

### Task 2: 裁剪非 Codex 平台与死负载

**Files:**
- Delete: `install-zcode.ps1`, `install-cursor.ps1`, `install-claude.ps1`, `install-workbuddy.ps1`, `install-workbuddy.cmd`, `install-dsh.ps1`, `install-doubao.ps1`
- Delete: `dsh-lazy-pack-v5/`, `codex-skills-v5/`, `codex-bundle-v5/`, `提示词副本/`, `memory/`
- Delete: `fj_tool.py`, `fj_tool.spec`, `requirements.txt`, `build.cmd`, `build-release.ps1`, `run_dev.cmd`
- Delete: non-Codex prompt variants and obsolete assets

**Steps:**
1. 删除平台安装器和非 Codex bundles。
2. 删除旧 Python/PyInstaller 主线。
3. 删除重复提示词副本和未打包资源。
4. 运行静态边界测试，确认剩余失败仅来自代码引用和品牌。

### Task 3: 重构 React 为单 Codex 产品

**Files:**
- Modify: `src/data/targets.ts`
- Modify: `src/App.tsx`
- Modify: `src/pages/InstallPage.tsx`
- Modify: `src/pages/TutorialPage.tsx`
- Modify: `src/pages/ProfilePage.tsx`
- Modify: `src/lib/hs.ts`
- Modify: `src/vite-env.d.ts`

**Steps:**
1. 将目标表改为唯一 Codex 目标和唯一 Jack 版本。
2. 删除多平台导航、QQ/中转/帮助入口和免费/Pro 分支。
3. 将 `window.hs` 改为 `window.jack`。
4. 将教程、状态、个人中心改为 Jack Codex 文案。
5. 运行 `npm run build`，修复 TypeScript/Vite 错误。

### Task 4: 重构 Electron 主进程

**Files:**
- Rewrite: `electron/main.cjs`
- Modify: `electron/preload.cjs`

**Steps:**
1. 只保留 Codex home 探测、状态、安装、卸载、Skills 列表、重启和窗口生命周期。
2. 删除 WorkBuddyGuard、多平台调度、任意 URL 外链和旧截图索引。
3. IPC 对 target/prompt/disabled skill 做白名单与路径验证。
4. 启用 Electron sandbox，并保持 context isolation、禁用 node integration。
5. 状态文件改为 `jack-desktop-state.json`；读取一次旧状态仅用于迁移。
6. 运行静态测试和 Vite 构建。

### Task 5: 重写 Codex 安装器

**Files:**
- Rewrite: `install.ps1`
- Replace: `scripts/clear-injected-prompts.ps1`
- Rewrite: `portable-uninstall.ps1`

**Steps:**
1. 校验 `CodexHome`、`SourcePrompt`、`SkillsSource`，拒绝越界路径。
2. 精确备份 `config.toml` 和 `AGENTS.md`，保存 SHA-256 与安装清单。
3. 只更新 `model_instructions_file` 和 Jack marker 块。
4. 复制 Jack 管理的 Skills；同名非 Jack 目录先备份，不使用 `/MIR`。
5. 不禁用、不删除用户自有 Skills 或无关 `[[skills.config]]`。
6. 卸载只按状态清单移除 Jack 文件并恢复原配置。
7. 兼容识别旧寒霜 marker，但不做跨平台扫描。
8. 执行临时 `CODEX_HOME` 回归测试。

### Task 6: 统一 Jack 品牌与提示词

**Files:**
- Create: `jack-codex-v1.md`
- Modify: `package.json`, `package-lock.json`, `variant.json`
- Modify: `scripts/build.mjs`, `scripts/after-pack.js`
- Modify: `build/installer.nsh`
- Modify: `README.md`, `LICENSE`
- Replace: `src/assets/brand.png`, `build/icon.png`, `build/icon.ico`

**Steps:**
1. 从现有 Codex 提示词提炼唯一 Jack 版本，身份和激活词统一为 Jack。
2. 将产品名、包名、appId、安装包、快捷方式和 PE 元数据改为 Jack。
3. 保留原 MIT 版权并追加 Jack 修改声明。
4. 创建中性文字图标，替换“寒”视觉资产。
5. 更新 README 为 Codex 单平台安装、卸载和构建说明。
6. 运行旧品牌扫描，仅许可证和迁移 allowlist 可命中。

### Task 7: 收敛唯一 Codex Skills 库

**Files:**
- Rename/Modify: `codex-skills-v4/` → `codex-skills/`
- Modify: affected `SKILL.md` and routing references

**Steps:**
1. 仅保留一个 `codex-skills` 目录。
2. 删除或改写 Claude/Cursor 专用注册说明。
3. 将 `seagull-*` 品牌技能重命名为中性名称，并原子更新 `$seagull-*` 引用；若交叉引用复杂则从发行清单排除。
4. 扫描 Skills 中的可执行下载器、`Invoke-Expression` 和自动安装入口，移除高风险脚本。
5. 验证每个一级 Skill 目录含合法 `SKILL.md`。

### Task 8: 构建与发布验收

**Files:**
- Modify: `tests/validate-package.mjs`
- Modify: `README.md`

**Steps:**
1. 运行 `npm install` 或 `npm ci`。
2. 运行 `npm test`。
3. 运行 `npm run build`。
4. 在临时 `CODEX_HOME` 执行安装→重复安装→升级→卸载。
5. 比对预置用户文件与自有 Skill 未被修改。
6. 检查 Git 状态和发行资源清单。
7. 生成最终变更摘要与已知兼容项。
