import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const materialTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/MaterialTab.tsx"),
  "utf8",
);
const wikiFormat = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/wikiFormat.ts"),
  "utf8",
);
const overviewTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/OverviewTab.tsx"),
  "utf8",
);
const sourceDrawer = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/WikiPageSourcesDrawer.tsx"),
  "utf8",
);
const zh = JSON.parse(
  fs.readFileSync(path.join(root, "src/app/opspilot/locales/zh.json"), "utf8"),
);

assert.doesNotMatch(
  materialTab,
  /const handleIngest|t\("wiki\.ingest"\)/,
  "the material list must expose one unified build action, not a parse action",
);
assert.match(
  wikiFormat,
  /status === ['"]parsing['"] \|\| status === ['"]building['"][^\n]+return ['"]building['"]/,
  "the internal parsing stage must display as building",
);
assert.match(
  wikiFormat,
  /return ['"]pending['"]/,
  "pending, parsed, and updated materials must display as unbuilt",
);
assert.match(
  wikiFormat,
  /status === ['"]parse_failed['"][\s\S]{0,180}status === ['"]build_failed['"][\s\S]{0,240}return ['"]failed['"]/,
  "internal parse and generation failures must display as build failed",
);
assert.match(
  materialTab,
  /MATERIAL_STATUS_META\[materialDisplayStatus\(s\)\]/,
  "the material list must use the shared four-state projection",
);
assert.match(
  overviewTab,
  /displayMatStatus[\s\S]{0,500}materialDisplayStatus\(status\)/,
  "the overview must aggregate internal stages into the same four states",
);
assert.doesNotMatch(
  sourceDrawer,
  /<Tag className="m-0">\{source\.material\.status\}<\/Tag>/,
  "source details must not expose internal status keys",
);
assert.match(
  sourceDrawer,
  /MATERIAL_STATUS_META\[[\s\S]{0,120}materialDisplayStatus\(source\.material\.status\)[\s\S]{0,40}\]/,
  "source details must display the shared four-state projection",
);
assert.equal(zh.wiki.statusPending, "未构建");
assert.equal(zh.wiki.statusBuilding, "构建中");
assert.equal(zh.wiki.statusBuilt, "构建成功");
assert.equal(zh.wiki.statusFailed, "构建失败");

console.log("wiki material unified build validation passed");
