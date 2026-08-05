import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const modal = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/WikiModifyModal.tsx"),
  "utf8",
);

assert.match(modal, /const isEditing = Boolean\(initialValues\?\.id\);/);
assert.match(
  modal,
  /const \[templateSchemaMd,\s*setTemplateSchemaMd\] = useState\(["']{2}\)/,
);
assert.match(
  modal,
  /const submitValues = \{[\s\S]*\.\.\.values,[\s\S]*schema_md: templateSchemaMd/,
);

for (const field of ["template_key", "purpose_md", "schema_md"]) {
  assert.match(modal, new RegExp(`delete submitValues\\.${field};`));
}

assert.match(modal, /!\s*isEditing && \(/);
assert.match(
  modal,
  /label=\{t\(["']wiki\.template["']\)\}[\s\S]*name=["']template_key["']/,
);
assert.match(
  modal,
  /label=\{t\(["']wiki\.purpose["']\)\}[\s\S]*name=["']purpose_md["']/,
);
assert.doesNotMatch(
  modal,
  /label=\{t\(["']wiki\.schema["']\)\}[\s\S]*name=["']schema_md["']/,
  "Schema must be configured by the structured editor, not a second free-text field",
);

console.log("wiki modify modal edit-only fields hidden validation passed");
