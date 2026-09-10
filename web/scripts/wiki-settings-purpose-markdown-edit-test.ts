import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const settingsTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/SettingsTab.tsx"),
  "utf8",
);

assert.match(
  settingsTab,
  /import MarkdownRenderer from ["']@\/components\/markdown["']/,
  "SettingsTab should render purpose/schema as markdown",
);
assert.doesNotMatch(
  settingsTab,
  /WikiStructureEditor/,
  "Settings must not mount a separate directory structure editor",
);
assert.match(
  settingsTab,
  /EditOutlined/,
  "SettingsTab should expose edit icon for purpose/schema markdown",
);
assert.match(settingsTab, /Tooltip/, "Edit icon should have a tooltip");
assert.match(
  settingsTab,
  /const \[purposeEditing,\s*setPurposeEditing\] = useState\(false\)/,
  "Purpose tab should default to read mode",
);
assert.match(
  settingsTab,
  /const \[purposePreview,\s*setPurposePreview\] = useState\(["']{2}\)/,
  "Read mode should use loaded purpose snapshot",
);
assert.match(
  settingsTab,
  /const \[schemaPreview,\s*setSchemaPreview\] = useState\(["']{2}\)/,
  "Read mode should use loaded schema snapshot",
);
assert.doesNotMatch(
  settingsTab,
  /Form\.useWatch\(["']purpose_md["'], form\)/,
  "Read mode must not depend on unmounted purpose form item",
);
assert.doesNotMatch(
  settingsTab,
  /Form\.useWatch\(["']schema_md["'], form\)/,
  "Read mode must not depend on unmounted schema form item",
);
assert.match(
  settingsTab,
  /setPurposePreview\(kb\.purpose_md \|\| ["']{2}\)/,
  "Load should fill purpose markdown preview",
);
assert.match(
  settingsTab,
  /setSchemaPreview\(kb\.schema_md \|\| ["']{2}\)/,
  "Load should fill schema markdown preview",
);
assert.match(
  settingsTab,
  /const handleCancelPurposeEdit = \(\) => \{/,
  "Edit mode should support cancel",
);
assert.match(
  settingsTab,
  /purpose_md: purposePreview/,
  "Cancel should restore purpose form field",
);
assert.match(
  settingsTab,
  /schema_md: schemaPreview/,
  "Cancel should restore schema form field",
);
assert.match(
  settingsTab,
  /setPurposeEditing\(false\)/,
  "Save or cancel should return to read mode",
);
assert.match(
  settingsTab,
  /<MarkdownRenderer content=\{content\} \/>/,
  "Read mode should use MarkdownRenderer",
);
assert.match(
  settingsTab,
  /purposeEditing \? \(/,
  "Purpose pane should switch between edit and read mode",
);
assert.match(
  settingsTab,
  /setPurposeEditing\(true\)/,
  "Edit icon should switch to edit mode",
);
assert.match(
  settingsTab,
  /onClick=\{handleCancelPurposeEdit\}/,
  "Edit mode should render cancel action",
);
assert.match(
  settingsTab,
  /t\(["']common\.cancel["']\)/,
  "Cancel action should use i18n text",
);
assert.match(
  settingsTab,
  /name=["']purpose_md["'][\s\S]*autoSize=\{false\}/,
  "Edit mode purpose textarea uses a fixed height",
);
assert.match(
  settingsTab,
  /name=["']schema_md["'][\s\S]*autoSize=\{false\}/,
  "Edit mode schema textarea uses a fixed height",
);
assert.match(
  settingsTab,
  /overflow-y-auto/,
  "Purpose and schema cards scroll internally",
);
assert.match(
  settingsTab,
  /grid-cols-1 gap-(?:x-)?6 lg:grid-cols-2/,
  "Purpose & Schema should use a two-column layout",
);
assert.match(
  settingsTab,
  /renderMarkdownCard\(t\(["']wiki\.purpose["']\),\s*purposePreview\)/,
  "Read mode should preview purpose markdown",
);
assert.match(
  settingsTab,
  /renderMarkdownCard\(t\(["']wiki\.schema["']\),\s*schemaPreview\)/,
  "Read mode should preview schema markdown",
);
assert.doesNotMatch(
  settingsTab,
  /WikiStructureEditor/,
  "Settings must not mount a separate directory structure editor",
);
assert.doesNotMatch(
  settingsTab,
  /key:\s*["']structure["']/,
  "Settings must not expose a directory-structure tab",
);

console.log("wiki settings two-column purpose and schema validation passed");
