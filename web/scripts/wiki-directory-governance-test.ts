import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const read = (relativePath: string) =>
  fs.readFileSync(path.join(root, relativePath), "utf8");

const request = read("src/utils/request.ts");
const api = read("src/app/opspilot/api/wiki.ts");
const settings = read("src/app/opspilot/components/wiki/SettingsTab.tsx");
const pageTab = read("src/app/opspilot/components/wiki/PageTab.tsx");
const directoryQuery = read(
  "src/app/opspilot/components/wiki/useWikiDirectoryQuery.ts",
);
const graphTab = read("src/app/opspilot/components/wiki/GraphTab.tsx");
const impactDrawer = read(
  "src/app/opspilot/components/wiki/WikiDirectoryImpactDrawer.tsx",
);

assert.match(request, /export class HandledRequestError extends Error/);
assert.match(request, /status\?: number/);
assert.match(request, /code\?: string/);
assert.match(request, /details\?: unknown/);
assert.match(request, /payload\?: unknown/);
assert.match(
  request,
  /new HandledRequestError\(messageText,[\s\S]*status,[\s\S]*code: payload\?\.code,[\s\S]*details: payload\?\.details,[\s\S]*payload/,
  "409/CAS errors must retain HTTP and service details",
);

assert.match(api, /const fetchDirectoryTree =/);
assert.match(api, /directory\/tree/);
assert.match(api, /const enableDirectoryGovernance =/);
assert.match(api, /directory_enable/);
assert.match(api, /directory\/structure/);
assert.match(api, /directory\/operation_preview/);
assert.match(api, /directory\/operation_execute/);
assert.match(api, /target_directory_id: targetDirectoryId/);
assert.match(api, /base_generation_id: baseGenerationId/);
assert.match(api, /structure_version: structureVersion/);

assert.match(
  settings,
  /name=["']schema_md["']/,
  "Settings keeps schema as markdown, not structured editor",
);
assert.match(
  settings,
  /grid-cols-1 gap-(?:x-)?6 lg:grid-cols-2/,
  "Purpose & Schema remain a two-column markdown layout",
);
assert.doesNotMatch(
  settings,
  /<WikiStructureEditor/,
  "Settings must not embed structured Schema editor",
);
assert.match(
  pageTab,
  /const directoryScopeEnabled =[\s\S]*active_generation_id[\s\S]*structure_version/,
);
assert.doesNotMatch(
  pageTab,
  /migration_state === ["']enabled["']/,
  "Navigation must not be hidden by a second directory-enable state",
);
assert.match(pageTab, /<WikiDirectoryTree/);
assert.match(pageTab, /<WikiPageReadingPane/);
assert.match(pageTab, /<WikiPageMoveModal/);
assert.match(pageTab, /onSelectPage=\{\(pageId\) => setSelectedPageId\(pageId\)\}/);
assert.match(directoryQuery, /wiki_page/);
assert.match(directoryQuery, /selectedPageId/);
assert.match(directoryQuery, /setSelectedPageId/);

assert.match(directoryQuery, /latestQueryRef = useRef\(currentQuery\)/);
assert.match(directoryQuery, /pendingQueriesRef = useRef<string\[\]>\(\[\]\)/);
assert.match(directoryQuery, /new URLSearchParams\(latestQueryRef\.current\)/);
assert.match(directoryQuery, /pendingQueriesRef\.current\.push\(nextQuery\)/);

assert.match(graphTab, /directory_id: directoryId \?\? undefined/);
assert.match(graphTab, /include_descendants: includeDescendants/);

for (const code of [
  "operation_token_expired",
  "operation_token_invalid",
  "operation_token_binding_mismatch",
  "operation_token_replayed",
  "directory_operation_stale",
]) {
  assert.ok(
    impactDrawer.includes(`"${code}"`),
    `impact preview must classify ${code}`,
  );
}
assert.match(
  impactDrawer,
  /error\.status === 409 && payload\?\.retryable/,
  "only retryable 409 responses should invalidate the approved preview",
);

console.log("wiki directory governance frontend wiring validation passed");
