# Apple Minimal UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 将已确认的苹果式极简 V3 概念移植到正式 React/Electron 界面，并保留安装、重装、重启、卸载恢复、Skills 管理、教程与设置功能。

**Architecture:** 保持 Electron IPC 与 `jack` API 不变，仅重组 React 页面语义和应用级样式。以 `App.tsx` 提供统一桌面壳，四个页面继续负责各自业务；所有状态仍由现有 IPC 回调驱动，不引入新依赖。

**Tech Stack:** React 19、TypeScript、Vite、Lucide React、CSS。

---

### Task 1: 固化正式 UI 验收边界

**Files:**
- Modify: `tests/validate-package.mjs`

1. 增加断言：正式入口必须引用新的 `jack-shell`、卸载按钮文案和四个视图。
2. 运行 `npm run test:static`，确认旧实现下断言失败。
3. 实现后重新运行并确认通过。

### Task 2: 重构应用壳与导航

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/main.tsx`
- Modify: `src/styles/app.css`

1. 将现有 settings 外壳改为苹果式浅色桌面壳。
2. 保留 `codex / skills / tutorial / profile` 四个视图与所有 IPC 状态。
3. 增加 Codex 在线状态、版本、通知和免责声明的统一视觉。
4. 仅保留实际使用的基础样式导入，避免旧页面规则覆盖新设计。

### Task 3: 重构部署与卸载页

**Files:**
- Modify: `src/pages/InstallPage.tsx`

1. 实现概览标题、安装主卡、完整度、能力卡和活动日志。
2. 未安装时突出“安装 Jack Codex”；已安装时显示“重新安装”和“重启 Codex”。
3. 始终提供清晰的“卸载并恢复原配置”操作；点击后弹出二次确认。
4. 忙碌状态禁用安装、重启和卸载，错误状态展示日志。

### Task 4: 重构 Skills、教程与设置页

**Files:**
- Modify: `src/pages/SkillsPage.tsx`
- Modify: `src/pages/TutorialPage.tsx`
- Modify: `src/pages/ProfilePage.tsx`

1. Skills 使用搜索栏、统计、行式开关、全开/全关/重载/保存。
2. 教程改为四步卡片，并明确卸载恢复入口。
3. 设置页展示运行状态、版本、自动修复开关和退出工具。
4. 修正 Skills 类型导入为 `../lib/jack`。

### Task 5: 构建与交互回归

**Files:**
- Test: `tests/validate-package.mjs`
- Test: `tests/test-installer.ps1`

1. 运行 `npm run build`，解决 TypeScript/Vite 错误。
2. 运行 `npm test`，确认包边界和安装生命周期通过。
3. 用 Edge 渲染 `dist/index.html` 不可独立启动，因此以 Vite 构建输出和组件静态断言验收；Electron 壳功能由现有 IPC 测试覆盖。
4. 运行 `git diff --check`。
