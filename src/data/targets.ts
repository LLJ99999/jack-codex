import variantInfo from "../../variant.json";

export const APP_NAME = variantInfo.appName || "Jack Codex 工具";
export const APP_VERSION = variantInfo.version || "1.0.0";
export const PROMPT_FILE = "jack-codex-v1.md";

export type Version = {
  name: string;
  desc: string;
  file: string;
  recommended?: boolean;
  choices?: Version[];
};

export type Target = {
  id: "codex";
  nav: string;
  eyebrow: string;
  title: string;
  desc: string;
  versions: Version[];
  uninstallLabel: string;
  icon: string;
};

export const TARGETS: Target[] = [
  {
    id: "codex",
    icon: "J",
    nav: "Codex 配置",
    eyebrow: "JACK CODEX",
    title: "Jack Codex",
    desc:
      "将 Jack 指令写入本机 Codex 配置与 AGENTS.md，并安装随包 Skills。所有修改均限定在 CODEX_HOME，安装前自动备份。",
    uninstallLabel: "卸载 Jack 配置",
    versions: [
      {
        name: "Jack Codex v1",
        desc: "Codex 单平台指令与 Skills 包 · 激活词「Jack」",
        file: PROMPT_FILE,
        recommended: true,
      },
    ],
  },
];

export const TUTORIAL_TEXT = [
  "1. 点击“安装”，工具会备份 Codex 的 config.toml 与 AGENTS.md。",
  "2. 安装完成后点击“重启 Codex”。",
  "3. 在新会话中发送“Jack”检查指令是否加载。",
  "4. Skills 管理只调整 Jack 包安装的技能，不改动其他目录。",
  "5. 点击“卸载 Jack 配置”可恢复安装前状态。",
  "",
  "如设置了 CODEX_HOME，工具会优先使用该目录；否则使用用户主目录下的 .codex。",
].join("\n");

export const DISCLAIMER_TITLE = "使用确认";
export const DISCLAIMER_TEXT = [
  "Jack Codex 工具只修改本机 Codex 配置目录。",
  "",
  "安装前会保存原配置和文件哈希；卸载时只处理本工具状态清单记录的文件。",
  "请在安装前关闭正在写入配置的 Codex 进程，并保留生成的备份文件。",
].join("\n");
