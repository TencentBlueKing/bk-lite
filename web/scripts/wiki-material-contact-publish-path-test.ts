import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const buildService = fs.readFileSync(
  path.join(root, "server/apps/opspilot/services/wiki/build_service.py"),
  "utf8",
);
const materialBuild = fs.readFileSync(
  path.join(root, "server/apps/opspilot/services/wiki/generation_material_build_service.py"),
  "utf8",
);

assert.match(
  buildService,
  /def prepare_page_data_with_contact_facts\(/,
  "build service must expose per-page contact preparation before write",
);
assert.match(
  materialBuild,
  /prepare_page_data_with_contact_facts\(text,\s*page_data\)/,
  "material build must re-apply contact facts before staging or review",
);
assert.match(
  materialBuild,
  /published_pages_missing_contact_facts\(text,\s*publishable_page_payloads\)/,
  "material build must audit publishable pages for missing contact facts",
);

console.log("wiki material contact publish-path validation passed");
