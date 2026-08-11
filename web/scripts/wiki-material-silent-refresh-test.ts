import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const materialTab = fs.readFileSync(
  path.join(root, "src/app/opspilot/components/wiki/MaterialTab.tsx"),
  "utf8",
);

assert.match(
  materialTab,
  /const loadRequestSequenceRef = useRef\(0\)/,
  "material refreshes must discard responses from stale pages or knowledge bases",
);

assert.match(
  materialTab,
  /const loadScopeRef = useRef\(\{\s*kbId,\s*page,\s*pageSize,\s*nameQuery,\s*statusGroups:/,
  "refreshes must bind to the latest knowledge base, pagination, name, and status scope",
);

assert.match(
  materialTab,
  /const pendingSilentRefreshRef = useRef\(false\)/,
  "post-action refreshes must be coalesced while a foreground page request is active",
);

assert.match(
  materialTab,
  /const pollingRequestInFlightRef = useRef\(false\)/,
  "polling effects must share one in-flight lock across rerenders",
);
assert.match(
  materialTab,
  /if \(silent && loadingRequestSequenceRef\.current !== null\)[\s\S]{0,140}pendingSilentRefreshRef\.current = true[\s\S]{0,80}return null/,
  "a silent refresh must queue instead of superseding the foreground response",
);
assert.match(
  materialTab,
  /const \{[\s\S]{0,200}kbId: requestedKbId,[\s\S]{0,200}page: requestedPage,[\s\S]{0,200}pageSize: requestedPageSize,[\s\S]{0,200}nameQuery: requestedNameQuery,[\s\S]{0,200}statusGroups: requestedStatusGroups,[\s\S]{0,80}\} = loadScopeRef\.current/,
  "even callbacks from an older render must fetch the current list scope",
);
assert.match(
  materialTab,
  /if \(!silent\)\s*\{[\s\S]{0,120}setLoading\(true\)/,
  "only foreground page loads may show the table loading state",
);

assert.match(
  materialTab,
  /loadingRequestSequenceRef\.current = null[\s\S]{0,220}pendingSilentRefreshRef\.current = false[\s\S]{0,180}load\(\{ silent: true \}\)\.catch/,
  "the latest foreground request must flush one queued silent refresh",
);
assert.match(
  materialTab,
  /load\(\{\s*silent:\s*true\s*\}\)/,
  "polling and post-action refreshes must update rows silently",
);
assert.match(
  materialTab,
  /const lastPage = Math\.max\(1,\s*Math\.ceil\(res\.count\s*\/\s*requestedPageSize\)\)/,
  "refreshes must calculate the last valid page from the refreshed total",
);
assert.match(
  materialTab,
  /if \(requestedPage > lastPage\)[\s\S]{0,400}setPage\(lastPage\)/,
  "an out-of-range page must fall back to the last valid page",
);
assert.match(
  materialTab,
  /current:\s*page/,
  "the table pagination must remain controlled by the current page state",
);

assert.match(
  materialTab,
  /loadScopeRef\.current = \{[\s\S]{0,120}kbId,[\s\S]{0,80}page: p,[\s\S]{0,80}pageSize: ps,[\s\S]{0,80}nameQuery,[\s\S]{0,80}statusGroups,[\s\S]{0,40}\}[\s\S]{0,120}setPage\(p\)/,
  "user pagination changes must update the latest query scope before fetching",
);

assert.match(
  materialTab,
  /const silentPageCorrectionRef = useRef\(false\)/,
  "a page correction triggered by polling must remain silent",
);
assert.match(
  materialTab,
  /silentPageCorrectionRef\.current = silent[\s\S]{0,120}setPage\(lastPage\)/,
  "an out-of-range silent refresh must carry silent mode into the corrected page load",
);

assert.match(
  materialTab,
  /const silent = silentPageCorrectionRef\.current[\s\S]{0,160}silentPageCorrectionRef\.current = false[\s\S]{0,160}void load\(\{ silent \}\)/,
  "the corrected page load must consume and clear the silent refresh marker",
);

assert.doesNotMatch(
  materialTab,
  /void load\(\{ silent(?:: true)? \}\);/,
  "fire-and-forget refreshes must handle rejected requests",
);

const pollingBlock = materialTab.match(
  /\/\/ 排队中 \/ 构建中\(含 parsing\) 均静默轮询刷新列表状态。[\s\S]*?const openCreate/,
)?.[0];
assert.ok(pollingBlock, "material polling block must exist");
assert.match(
  pollingBlock,
  /load\(\{\s*silent:\s*true\s*\}\)/,
  "the polling timer must use a silent refresh",
);

assert.match(
  pollingBlock,
  /if \([\s\S]{0,120}!pollingRequestInFlightRef\.current[\s\S]{0,120}loadingRequestSequenceRef\.current === null[\s\S]{0,180}pollingRequestInFlightRef\.current = true[\s\S]{0,220}await load\(\{\s*silent:\s*true\s*\}\)[\s\S]{0,220}pollingRequestInFlightRef\.current = false/,
  "background polling must use one shared lock and yield to foreground requests",
);

assert.match(
  pollingBlock,
  /await load\(\{\s*silent:\s*true\s*\}\)[\s\S]{0,220}setTimeout\(poll, 3000\)/,
  "polling must schedule the next refresh only after the previous request settles",
);
assert.doesNotMatch(
  pollingBlock,
  /setInterval\(/,
  "polling must not overlap slow refresh requests",
);
assert.doesNotMatch(
  pollingBlock,
  /setLoading\(/,
  "polling must never toggle the table loading state directly",
);

console.log("wiki material silent refresh validation passed");
