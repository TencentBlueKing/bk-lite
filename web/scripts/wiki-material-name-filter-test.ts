import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const materialTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/MaterialTab.tsx"),
  "utf8",
);
const zh = JSON.parse(
  fs.readFileSync(path.join(root, "src/app/opspilot/locales/zh.json"), "utf8"),
);
const en = JSON.parse(
  fs.readFileSync(path.join(root, "src/app/opspilot/locales/en.json"), "utf8"),
);

assert.equal(zh.wiki.filterQuery, "查询");
assert.equal(en.wiki.filterQuery, "Query");

assert.match(
  materialTab,
  /const \[nameDraft, setNameDraft\] = useState\(""\)/,
  "name filter draft must not query until confirmed",
);
assert.match(
  materialTab,
  /const \[statusDraft, setStatusDraft\] = useState/,
  "status filter draft must not query until confirmed",
);
assert.match(
  materialTab,
  /const \[nameQuery, setNameQuery\] = useState\(""\)/,
  "applied name query must drive the list request",
);
assert.match(
  materialTab,
  /applyMaterialFilters/,
  "material filters must apply through an explicit query action",
);
assert.match(
  materialTab,
  /t\("wiki\.filterQuery"\)/,
  "the toolbar must expose a query button",
);
assert.match(
  materialTab,
  /requestedNameQuery\.trim\(\)[\s\S]{0,80}\{\s*search:\s*requestedNameQuery\.trim\(\)\s*\}/,
  "list requests must pass the applied name as search",
);
assert.match(
  materialTab,
  /onChange=\{\(values: MaterialDisplayStatus\[\]\) => \{\s*setStatusDraft\(values\);\s*\}\}/,
  "status select changes must only update draft state",
);
assert.doesNotMatch(
  materialTab,
  /filters:\s*MATERIAL_DISPLAY_STATUS_OPTIONS/,
  "status column must not auto-filter on header clicks",
);

console.log("wiki material name filter validation passed");
