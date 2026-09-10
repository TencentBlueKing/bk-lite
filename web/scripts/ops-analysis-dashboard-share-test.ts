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
const continuePage = fs.readFileSync(
  'src/app/ops-analysis/share/continue/page.tsx',
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
const shareModeContext = fs.readFileSync(
  'src/app/ops-analysis/context/shareMode.tsx',
  'utf8',
);
const comTable = fs.readFileSync(
  'src/app/ops-analysis/components/widgets/comTable.tsx',
  'utf8',
);
const networkTopo = fs.readFileSync(
  'src/app/ops-analysis/components/widgets/networkStatusTopology/index.tsx',
  'utf8',
);
const rootLayout = fs.readFileSync('src/app/layout.tsx', 'utf8');

assert.match(toolbar, /shareMode\?: boolean/);
assert.match(toolbar, /shareLoading\?: boolean/);
assert.match(toolbar, /onOpenShare\?: \(\) => void/);
assert.match(toolbar, /!shareMode &&/);
assert.match(toolbar, /loading=\{shareLoading\}/);
assert.match(dashboard, /shareSessionId\?: string/);
assert.match(dashboard, /useCanvasShareAction\(['"]dashboard['"]\)/);
assert.match(dashboard, /openShare/);
assert.doesNotMatch(dashboard, /ShareDialog|shareDialog/);
assert.match(apiSource, /const createShare = useCallback/);
assert.match(apiSource, /prepareShareToken/);
assert.match(apiSource, /credentials:\s*['"]include['"]/);
assert.doesNotMatch(apiSource, /listShares|revokeShare|duration_seconds|permanent/);
assert.match(toolbar, /t\(['"]dashboard\.share['"]\)/);

const shareAction = fs.readFileSync(
  'src/app/ops-analysis/hooks/useCanvasShareAction.tsx',
  'utf8',
);
assert.match(shareAction, /createShare\(resourceType, resourceId\)/);
assert.match(shareAction, /t\(['"]dashboard\.shareLinkCopied['"]\)/);
assert.match(shareAction, /t\(['"]dashboard\.shareCopyFailed['"]\)/);
assert.match(shareAction, /t\(['"]dashboard\.shareCreateFailed['"]\)/);
assert.doesNotMatch(
  shareAction,
  /Exclude<CanvasShareResourceType,\s*['"]report['"]>/,
);
assert.match(shareAction, /function useCanvasShareAction\(resourceType: CanvasShareResourceType\)/);

const screenToolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx',
  'utf8',
);
const screenPage = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/screen/index.tsx',
  'utf8',
);
const topologyToolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx',
  'utf8',
);
const topologyPage = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/topology/index.tsx',
  'utf8',
);
const architectureToolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/architecture/components/toolbar.tsx',
  'utf8',
);
const architecturePage = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/architecture/index.tsx',
  'utf8',
);
const reportPage = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/report/index.tsx',
  'utf8',
);

assert.match(screenToolbar, /onOpenShare/);
assert.match(screenToolbar, /if \(!shareMode && editMode\)/);
assert.match(screenToolbar, /!shareMode && onOpenShare/);
assert.match(screenPage, /useCanvasShareAction\(['"]screen['"]\)/);
assert.match(topologyToolbar, /onOpenShare/);
assert.match(topologyToolbar, /!shareMode && !isEditMode && onOpenShare/);
assert.match(topologyPage, /useCanvasShareAction\(['"]topology['"]\)/);
assert.match(architectureToolbar, /onOpenShare/);
assert.match(architectureToolbar, /!shareMode && !isEditMode && onOpenShare/);
assert.match(architecturePage, /useCanvasShareAction\(['"]architecture['"]\)/);
const networkToolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/networkTopology/components/networkToolbar.tsx',
  'utf8',
);
const networkPage = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/networkTopology/index.tsx',
  'utf8',
);
assert.match(networkToolbar, /onOpenShare/);
assert.match(networkToolbar, /!shareMode && !editMode && onOpenShare/);
assert.match(networkPage, /useCanvasShareAction\(['"]networkTopology['"]\)/);
assert.match(networkPage, /onOpenShare=/);
const reportToolbar = fs.readFileSync(
  'src/app/ops-analysis/(pages)/view/report/components/reportToolbar.tsx',
  'utf8',
);
assert.match(reportPage, /useCanvasShareAction\(['"]report['"]\)/);
assert.match(reportPage, /onOpenShare/);
assert.match(reportToolbar, /ShareAltOutlined/);
assert.match(reportToolbar, /if \(!shareMode && editing\)/);
assert.match(reportToolbar, /\{onOpenShare && \(/);

assert.match(tokenPage, /prepareShareToken/);
assert.match(tokenPage, /share\/continue\?state=/);
assert.doesNotMatch(tokenPage, /callbackUrl: window\.location\.href/);
assert.match(continuePage, /exchangeShare\(\{ state \}\)/);
assert.match(sessionPage, /ShareModeProvider/);
assert.match(sessionPage, /ShareOrganizationProvider/);
assert.match(sessionPage, /ShareDataSourceProvider/);
const shareDto = fs.readFileSync(
  'src/app/ops-analysis/types/dashboardShare.ts',
  'utf8',
);
const filterBar = fs.readFileSync(
  'src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx',
  'utf8',
);
assert.match(shareDto, /space_id\?: number/);
assert.match(shareDto, /group_tree\?: Group\[\]/);
assert.match(filterBar, /treeData=\{organizationTreeData\}/);
assert.match(filterBar, /convertGroupTreeToTreeSelectData/);
assert.match(dashboard, /resolveCanvasOrganizationId/);
assert.match(screenPage, /organizationId: shareOrganizationSeed/);
assert.match(reportPage, /fillMissingOrganizationFilterValues/);
assert.match(topologyPage, /organizationId: shareOrganizationSeed/);
assert.match(
  sessionPage,
  /DS_TYPES = new Set\(\[['"]dashboard['"], ['"]topology['"], ['"]screen['"], ['"]report['"]\]\)/,
);
assert.match(sessionPage, /case ['"]report['"]/);
assert.doesNotMatch(sessionPage, /第一阶段不渲染 report/);
assert.match(shareModeContext, /useShareMode/);
assert.match(comTable, /useShareMode/);
assert.match(comTable, /shareNavigationDisabled/);
assert.match(networkTopo, /useShareMode/);
assert.match(tokenPage, /t\(['"]dashboard\.shareInvalid['"]\)/);
assert.match(tokenPage, /t\(['"]dashboard\.shareOpening['"]\)/);
assert.match(sessionPage, /t\(['"]dashboard\.shareInvalid['"]\)/);
assert.match(sessionPage, /t\(['"]dashboard\.shareLoading['"]\)/);
assert.doesNotMatch(tokenPage, /已被撤销|过期/);
assert.doesNotMatch(sessionPage, /已被撤销|过期/);
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
assert.match(
  rootLayout,
  /!hideConsoleTopNav && \(/,
  'share destinations reuse hideConsoleTopNav to omit TopMenu',
);
const consoleLayoutResolve = fs.readFileSync(
  'src/console-layout/resolve.ts',
  'utf8',
);
const hideConsoleTopNavFn = consoleLayoutResolve.match(
  /export const shouldHideConsoleTopNav[\s\S]*?^};/m,
)?.[0];
assert.ok(
  hideConsoleTopNavFn,
  'shouldHideConsoleTopNav definition must be present',
);
assert.match(
  hideConsoleTopNavFn,
  /pathname\.startsWith\(['"]\/ops-analysis\/share\/['"]\)/,
  'share destinations must hide the console top nav',
);
assert.doesNotMatch(
  hideConsoleTopNavFn,
  /\/ops-analysis\/view/,
  'in-product ops-analysis view must keep console top nav',
);
const webchatVisibility = fs.readFileSync(
  'src/app/(core)/components/global-webchat/visibility.ts',
  'utf8',
);
assert.match(
  webchatVisibility,
  /GLOBAL_WEBCHAT_EXCLUDED_PATH_PREFIXES[\s\S]*['"]\/ops-analysis\/share\/['"]/,
  'share destinations must exclude the global assistant',
);
const sessionExpiry = fs.readFileSync('src/utils/sessionExpiry.ts', 'utf8');
assert.match(
  sessionExpiry,
  /dashboard_share\/prepare\//,
  'prepare without bearer must not trigger session-expired modal',
);
assert.equal(
  fs.existsSync('src/app/ops-analysis/(pages)/view/dashBoard/components/shareDialog.tsx'),
  false,
  'share dialog component must be removed',
);

console.log('ops-analysis dashboard share contracts passed');
