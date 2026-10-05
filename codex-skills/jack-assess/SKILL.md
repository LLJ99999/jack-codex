---
name: jack-assess
description: Jack Ops assess leaf. Rank every unassessed asset for exploitability into the fact store. Do not validate vulns. Use after recon has logged assets.
triggers:
  - 资产梳理
  - 易打性
  - jack-assess
---

# Jack Assess（叶子）

加载 `$jack-ops` 纪律。`OPS=python3 $CODEX_HOME/skills/jack-ops/scripts/jack_ops.py`

## 职责

`$OPS asset-list --todo` 一条一条过，不允许抽样。

```
$OPS asset-assess --id N --priority high|medium|low --potential 预期成果 --reason 依据 --agent assess
$OPS asset-test --id N --status untested --test "已评估：摘要"
```

排序：已知 Nday RCE 中间件 ＞ 未授权/管理后台 ＞ 暴露库/缓存 ＞ 弱口令端 ＞ 官网静态站。
边缘资产优先于官方门户。

缺端口/标题时用 httpx/nmap -sV 补最小信息，这是为了评估，不是漏洞验证。
疑似线索写 `--surface`，交给 vuln。

## 收口

`--todo` 为空。给指挥 High 前 20 条（id、IP、端口、理由、预期成果）+ 总数。
禁止再委派。

<!-- JACK-OPS-COMMON:BEGIN -->

# Jack Ops 公共纪律（所有作战角色共用）

脚本：`codex-skills/jack-ops/scripts/jack_ops.py`
库根：`$JACK_OPS_HOME` 或 `$CODEX_HOME/.jack-ops` 或 `~/.codex/.jack-ops`
别名：`OPS="python3 <skill-dir>/scripts/jack_ops.py"`

## 未落库 = 没发生

每条发现必须进库。口头“打通了”不算。指挥核对 id，对不上就打回补库。

```
$OPS open <靶标> [--scope CIDR]
$OPS next                          # 指挥：该派谁
$OPS asset-add --ip IP --name HOST --url URL --ports 8080:http --tool nmap --provenance active
$OPS asset-assess --id N --priority high|medium|low --potential 预期成果 --reason 依据
$OPS asset-test --id N --status testing|tested|blocked|abandoned|no_surface --test "结论"
$OPS vuln-add --title T --severity high --target URL --evidence 回显 --asset N --status confirmed
$OPS evidence-add --request "原始HTTP" --response "摘要" --vuln N --url URL
$OPS cred-add --host H --user U --secret P --source 弱口令 --tool hydra
$OPS access-add --host H --method web-login --user U --privilege admin
$OPS shell-add --url URL --type behinder|godzilla --password KEY --privilege www-data
$OPS tunnel-add --kind suo5 --listen 127.0.0.1:1080 --entry URL --entry-kind target-http --reach 10.0.0.0/8 --command "原文"
$OPS step-add --stage recon|internet|boundary|internal|target --title 一句话 --tool "命令原文" --result "回显"
$OPS poc-search --q 组件 --component Tomcat
$OPS poc-add --title T --component C --verified --content "通用POC"
$OPS sessions / $OPS chain / $OPS report / $OPS report-md / $OPS info
```

`step-add` 缺 `--tool` 或 `--result` 直接失败。这是报告复现的唯一来源。

## 查库再动手

测任何资产前：

1. `$OPS asset-list --q IP` 看 `test_status` / `priority` / `surface`
2. `$OPS vuln-list --asset N` 看已有漏洞
3. `$OPS sessions` 看现成马 / 隧道 / 凭据
4. `$OPS poc-search --q 组件` 先查知识库，命中再用，不要重搓

`tested` 且无新线索 → 跳过。`abandoned` → 跳过。重测把理由追加进 `--test`。

## 阶段

`recon` 信息收集 → `internet` 外网权限 → `boundary` 边界突破 → `internal` 内网权限 → `target` 靶标。
指挥用 `$OPS next` 决定派谁，用 `$OPS stage --set <code>` 推进。没有当前阶段产物，不派下一阶段。

## 入口口径

- 马：`behinder` / `godzilla`。其它类型入库会带 warning，不算可交付入口。
- 隧道 `entry-kind`：`target-http`（经目标 WebShell）/ `target-outbound`（目标反弹）/ `target-agent`（已控进程转发）/ `self-only`（只在自己机器上，**不算突破**）。空 = 待确认，不算突破。
- 账号：只有凭据不算。必须实际登录成功再 `access-add method=web-login`。
- 自建/自注册账号写进 note，不当成果。

## 交付口径（角色回报固定四段）

1. 结论：拿到/没拿到，带资产
2. 落库 id：asset / vuln / step / shell / tunnel
3. 数字：覆盖多少、测了多少
4. 卡点与下一步

不确定的不要写成成果。

<!-- JACK-OPS-COMMON:END -->
