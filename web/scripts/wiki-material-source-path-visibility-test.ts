import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const materialTab = fs.readFileSync(
  path.join(process.cwd(), "src/app/opspilot/components/wiki/MaterialTab.tsx"),
  "utf8",
);

assert.doesNotMatch(
  materialTab,
  /record\.source_relative_path/,
  "the material list must not display the internal source-relative path",
);
assert.doesNotMatch(
  materialTab,
  /detail\.material\.source_relative_path/,
  "the material detail drawer must not expose the internal source-relative path",
);
assert.match(
  materialTab,
  /source_relative_path:\s*file\.webkitRelativePath\?\.trim\(\) \|\| file\.name/,
  "folder uploads must still retain the source-relative path as internal provenance",
);

console.log("wiki material source path visibility validation passed");
