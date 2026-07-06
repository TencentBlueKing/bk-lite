import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

/**
 * 回归测试：CMDB 资产详情·应用拓扑（AppTopology）整体接线完整性。
 *
 * 背景：用户在前端 CMDB → 资产详情 → 「应用」模型下的应用拓扑视图。修复
 * `2d9173467` 打包问题时误删了两处 wired 代码：
 *   - 主页面 `relationships/page.tsx`：以右上 Segmented 切换到应用拓扑/IP 视图。
 *   - 左侧 `side-menu.tsx`         ：以快捷入口一键跳到该应用拓扑子视图。
 *
 * 本测试锁定这两次失效，避免回归：
 *   页面文件：
 *     - `ApplicationResourceOverview`（应用拓扑）的 3 件套
 *     - `IpamMatrix`（IP 视角）的 2 件套（import 已在）
 *   侧栏文件：
 *     - `themes.includes('app_overview')` → shortcuts 中的 `tab: 'appOverview'` 推送
 *     - 注释里仍列出「应用拓扑」字样
 *
 * 失败即视为接线缺失，发布前必须看到脚本通过。
 */

const webRoot = path.resolve('src/app/cmdb/(pages)/assetData');
const pagePath = path.join(webRoot, 'detail/relationships/page.tsx');
const sideMenuPath = path.join(webRoot, 'components/sub-layout/side-menu.tsx');

const pageSrc = fs.readFileSync(pagePath, 'utf8');
const sideMenuSrc = fs.readFileSync(sideMenuPath, 'utf8');

const failures = [];

// —— ApplicationResourceOverview（在 relationships/page.tsx）——

if (!/import\s+ApplicationResourceOverview\s+from\s+['"][^'"]*applicationResourceOverview[^'"]*['"]/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 缺少 `import ApplicationResourceOverview from "./applicationResourceOverview"`');
}

if (!/themes\.includes\(\s*['"]app_overview['"]\s*\)\s*\?\s*\[\{[\s\S]*?value:\s*['"]appOverview['"]/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] Segmented options 缺少 `themes.includes("app_overview")` 分支');
}

if (!/['"]appOverview['"][\s\S]{0,200}<ApplicationResourceOverview/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 内容区缺少 `activeTab === "appOverview"` 渲染分支');
}

// —— IpamMatrix（在 relationships/page.tsx）——

if (!/themes\.includes\(\s*['"]ipam['"]\s*\)\s*\?\s*\[\{[\s\S]*?value:\s*['"]ipam['"]/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] Segmented options 缺少 `themes.includes("ipam")` 分支');
}

if (!/['"]ipam['"][\s\S]{0,200}<IpamMatrix/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 内容区缺少 `activeTab === "ipam"` 渲染分支');
}

// —— 应用拓扑快捷入口（在 side-menu.tsx）——

if (!/themes\.includes\(\s*['"]app_overview['"]\s*\)/.test(sideMenuSrc)) {
  failures.push('[side-menu.tsx] 左侧 shortcuts 缺少 `themes.includes("app_overview")` 条件分支');
}

const shortcutPushRe = /themes\.includes\(\s*['"]app_overview['"]\s*\)[\s\S]{0,200}?list\.push\(\s*\{[\s\S]*?tab:\s*['"]appOverview['"]/;
if (!shortcutPushRe.test(sideMenuSrc)) {
  failures.push('[side-menu.tsx] shortcuts 推送中缺少 `tab: "appOverview"` 字段');
}

const shortcutTitleRe = /themes\.includes\(\s*['"]app_overview['"]\s*\)[\s\S]{0,300}?title:\s*t\(\s*['"]Model\.applicationResourceOverview['"]/;
if (!shortcutTitleRe.test(sideMenuSrc)) {
  failures.push('[side-menu.tsx] shortcuts 推送中缺少 `t("Model.applicationResourceOverview")` 标题');
}

// 注释里"应用拓扑"四字必须存在（防止有人把这一行从设计上撕掉）
if (!sideMenuSrc.includes('应用拓扑')) {
  failures.push('[side-menu.tsx] 顶部 `// 左侧快捷入口` 注释缺少"应用拓扑"字样');
}

assert.equal(
  failures.length,
  0,
  '\n应用拓扑 / IP 视角 接线回归测试失败:\n  - ' + failures.join('\n  - ')
);

console.log('cmdb-app-overview-wiring test passed');
