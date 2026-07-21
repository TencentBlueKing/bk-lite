import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(
  resolve(process.cwd(), "src/app/cmdb/(pages)/assetSearch/page.tsx"),
  "utf8",
);

assert.match(
  pageSource,
  /const resetToLanding = \(\) => \{[\s\S]*?setSearchText\(''\);[\s\S]*?setShowSearch\(true\);[\s\S]*?\n  \};/,
  "搜索结果页应提供统一的首页重置动作",
);

assert.match(
  pageSource,
  /const handleTextChange = \(e: React\.ChangeEvent<HTMLInputElement>\) => \{[\s\S]*?if \(!nextSearchText\) \{[\s\S]*?resetToLanding\(\);[\s\S]*?\}/,
  "清空结果页搜索框时应自动返回首页",
);

assert.match(
  pageSource,
  /<Button[\s\S]*?icon=\{<ArrowLeftOutlined \/>\}[\s\S]*?onClick=\{resetToLanding\}[\s\S]*?\{t\('common\.backToHome'\)\}[\s\S]*?<\/Button>/,
  "搜索结果页应提供明确的“返回首页”按钮",
);

const resetBody = pageSource.match(
  /const resetToLanding = \(\) => \{([\s\S]*?)\n  \};/,
)?.[1];
assert.ok(resetBody, "应能读取首页重置动作");
assert.doesNotMatch(
  resetBody,
  /setHistoryList|setCaseSensitive|setRecentChanges|setFollowedAssets/,
  "返回首页不应清除搜索历史、匹配偏好或首页数据",
);

console.log("PASS cmdb-search-return-home");
