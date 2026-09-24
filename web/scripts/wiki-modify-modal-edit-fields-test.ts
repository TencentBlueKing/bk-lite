import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const modal = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/WikiModifyModal.tsx"),
  "utf8",
);

assert.doesNotMatch(modal, /template_key/);
assert.doesNotMatch(modal, /purpose_md/);
assert.doesNotMatch(modal, /schema_md/);
assert.doesNotMatch(modal, /fetchTemplates/);
assert.match(modal, /name=["']introduction["']/);
assert.match(modal, /wiki\.introductionRequired/);
assert.match(modal, /name=["']name["']/);
assert.match(modal, /name=["']llm_model["']/);

console.log("wiki modify modal introduction-only create fields validation passed");
