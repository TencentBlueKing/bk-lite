import assert from 'node:assert/strict';
import fs from 'node:fs';

const toolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardToolbar.tsx',
  'utf8',
);
const dashboard = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/dashBoard/index.tsx',
  'utf8',
);
const apiSource = fs.readFileSync(
  'src/app/ops-analysis/api/dashboardShare.ts',
  'utf8',
);
const tokenPage = fs.readFileSync(
  'src/app/ops-analysis/share/[token]/page.tsx',
  'utf8',
);
const sessionPage = fs.readFileSync(
  'src/app/ops-analysis/share/session/[sessionId]/shareDashboardPage.tsx',
  'utf8',
);
const dataSourceApi = fs.readFileSync(
  'src/app/ops-analysis/api/dataSource.ts',
  'utf8',
);
const opsAnalysisContext = fs.readFileSync(
  'src/app/ops-analysis/context/common.tsx',
  'utf8',
);
const rootLayout = fs.readFileSync('src/app/layout.tsx', 'utf8');

assert.match(toolbar, /shareMode\?: boolean/);
assert.match(toolbar, /shareLoading\?: boolean/);
assert.match(toolbar, /onOpenShare\?: \(\) => void/);
assert.match(toolbar, /!shareMode &&/);
assert.match(toolbar, /loading=\{shareLoading\}/);
assert.match(dashboard, /shareSessionId\?: string/);
assert.match(dashboard, /createShare/);
assert.match(dashboard, /t\(['"]dashboard\.shareLinkCopied['"]\)/);
assert.match(dashboard, /t\(['"]dashboard\.shareCopyFailed['"]\)/);
assert.match(dashboard, /t\(['"]dashboard\.shareCreateFailed['"]\)/);
assert.match(toolbar, /t\(['"]dashboard\.share['"]\)/);
assert.doesNotMatch(dashboard, /ShareDialog|shareDialog/);
assert.match(apiSource, /const createShare = useCallback/);
assert.doesNotMatch(apiSource, /listShares|revokeShare|duration_seconds|permanent/);
assert.match(tokenPage, /router\.replace\(`\/ops-analysis\/share\/session\/\$\{result\.session_id\}`\)/);
assert.match(tokenPage, /t\(['"]dashboard\.shareInvalid['"]\)/);
assert.match(tokenPage, /t\(['"]dashboard\.shareOpening['"]\)/);
assert.match(sessionPage, /t\(['"]dashboard\.shareInvalid['"]\)/);
assert.match(sessionPage, /t\(['"]dashboard\.shareLoading['"]\)/);
assert.doesNotMatch(tokenPage, /已被撤销|过期/);
assert.doesNotMatch(sessionPage, /已被撤销|过期/);
assert.match(sessionPage, /ShareDataSourceProvider/);
assert.match(
  sessionPage,
  /className=["']h-full w-full overflow-hidden["']/,
  'share session must fill the bounded root content area instead of adding another viewport height',
);
assert.match(dataSourceApi, /sharedAccess\.queryDataSource/);
assert.match(dataSourceApi, /sharedAccess\.getDataSourceDetails/);
assert.match(
  opsAnalysisContext,
  /if \(sharedAccess \|\| namespacesRequestingRef\.current\)/,
  'share mode must no-op refreshNamespaces instead of calling the namespace list API',
);
assert.match(
  opsAnalysisContext,
  /if \(sharedAccess\)[\s\S]*namespace_options[\s\S]*mergeNamespaces/,
  'share mode fetchNamespaces must hydrate from scoped data-source metadata',
);
assert.match(
  opsAnalysisContext,
  /if \(sharedAccess\)[\s\S]*namespace_options/,
  'share mode must hydrate namespaces from scoped data-source metadata',
);
assert.match(
  opsAnalysisContext,
  /rawDataSourcesRef\.current = scopedDataSources/,
  'share namespace hydration must see the data sources loaded in the same resource-sync cycle',
);
assert.match(
  rootLayout,
  /pathname\?\.startsWith\(['"]\/ops-analysis\/share\/['"]\)/,
  'authenticated share routes must bypass menu-based routing',
);
assert.match(
  rootLayout,
  /isDashboardShareRoute[\s\S]*h-screen overflow-hidden/,
  'share routes must bound the root layout to the viewport',
);
assert.equal(
  fs.existsSync('src/app/ops-analysis/(pages)/view/dashBoard/components/shareDialog.tsx'),
  false,
  'share dialog component must be removed',
);

console.log('ops-analysis dashboard share contracts passed');
