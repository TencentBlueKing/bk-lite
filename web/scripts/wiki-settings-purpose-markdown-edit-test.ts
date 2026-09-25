import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const settingsTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/SettingsTab.tsx"),
  "utf8",
);

assert.equal(
  fs.existsSync(path.join(root, "src/app/opspilot/components/wiki/WikiStructureEditor.tsx")),
  false,
  "unused WikiStructureEditor must be removed",
);
assert.doesNotMatch(
  settingsTab,
  /WikiStructureEditor/,
  "Settings must not mount a separate directory structure editor",
);
assert.doesNotMatch(
  settingsTab,
  /key:\s*["']purpose["']/,
  "Settings must not expose a purpose/schema tab",
);
assert.doesNotMatch(
  settingsTab,
  /key:\s*["']structure["']/,
  "Settings must not expose a directory-structure tab",
);
assert.doesNotMatch(settingsTab, /purpose_md/);
assert.doesNotMatch(settingsTab, /schema_md/);
assert.match(
  settingsTab,
  /name=["']introduction["']/,
  "Settings should keep a required introduction field",
);
assert.match(
  settingsTab,
  /wiki\.introductionRequired/,
  "Introduction validation should be required",
);
assert.match(
  settingsTab,
  /key:\s*["']basic["']/,
  "Settings should keep the basic info tab",
);
assert.match(
  settingsTab,
  /key:\s*["']danger["']/,
  "Settings should keep the danger zone tab",
);

console.log("wiki settings basic+danger introduction-only validation passed");
