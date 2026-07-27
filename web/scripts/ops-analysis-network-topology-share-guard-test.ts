import assert from 'node:assert/strict';
import fs from 'node:fs';

/**
 * 静态收口：分享态编辑 WeOps API 必须经 networkTopologyShareGuard 拦截，
 * 且 metric_values / link_runtime 不得被同一防护误伤。
 */
const apiSource = fs.readFileSync(
  'src/app/ops-analysis/api/networkTopology.ts',
  'utf8',
);
const guardSource = fs.readFileSync(
  'src/app/ops-analysis/api/networkTopologyShareGuard.ts',
  'utf8',
);
const indexSource = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/networkTopology/index.tsx',
  'utf8',
);
const sessionPage = fs.readFileSync(
  'src/app/ops-analysis/share/session/[sessionId]/shareDashboardPage.tsx',
  'utf8',
);

assert.match(apiSource, /useShareMode/);
assert.match(apiSource, /isNetworkTopologyShareAccess/);
assert.match(apiSource, /rejectNetworkTopologyEditApiInShareMode/);

const blocked = [
  'getNodeModels',
  'getNodes',
  'getNodeInterfaces',
  'getNodeMetrics',
  'getDimensionValues',
  'saveViewSets',
  'testConnection',
  'testSavedConnection',
] as const;

for (const api of blocked) {
  assert.match(
    apiSource,
    new RegExp(`rejectNetworkTopologyEditApiInShareMode\\(shareAccess, ['"]${api}['"]\\)`),
    `missing share guard for ${api}`,
  );
  assert.match(
    guardSource,
    new RegExp(`['"]${api}['"]`),
    `guard catalog missing ${api}`,
  );
}

assert.match(apiSource, /if \(shareRuntime\) \{\s*return shareRuntime\.getMetricValues/);
assert.match(apiSource, /if \(shareRuntime\) \{\s*return shareRuntime\.getLinkRuntime/);
assert.doesNotMatch(
  apiSource,
  /rejectNetworkTopologyEditApiInShareMode\(shareAccess, ['"]getMetricValues['"]\)/,
);
assert.doesNotMatch(
  apiSource,
  /rejectNetworkTopologyEditApiInShareMode\(shareAccess, ['"]getLinkRuntime['"]\)/,
);

assert.match(indexSource, /enabled: Boolean\(canvasId\) && !shareMode/);
assert.match(indexSource, /!shareMode && !isFullscreen/);
assert.match(sessionPage, /ShareNetworkTopologyRuntimeProvider/);
assert.match(sessionPage, /shareMode/);

console.log('ops-analysis-network-topology-share-guard-test: ok');
