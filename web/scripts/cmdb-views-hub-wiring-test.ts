import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Thin static wiring regression for CMDB primary views hub.
 * Asserts ViewCanvasHost embeds all five topic canvases and key contracts.
 */

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const hostPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/views/components/ViewCanvasHost.tsx'
);
const urlsPath = path.join(webRoot, 'src/app/cmdb/(pages)/views/viewUrls.ts');

const hostSrc = fs.readFileSync(hostPath, 'utf8');
const urlsSrc = fs.readFileSync(urlsPath, 'utf8');
const failures: string[] = [];

const requiredImports: { name: string; pattern: RegExp }[] = [
  {
    name: 'NetworkTopo',
    pattern: /import\s+NetworkTopo\s+from\s+['"][^'"]*networkTopo['"]/,
  },
  {
    name: 'ApplicationResourceOverview',
    pattern:
      /import\s+ApplicationResourceOverview\s+from\s+['"][^'"]*applicationResourceOverview['"]/,
  },
  {
    name: 'K8sResourceDetailsContent',
    pattern:
      /import\s+K8sResourceDetailsContent\s+from\s+['"][^'"]*K8sResourceDetailsContent['"]/,
  },
  {
    name: 'IpamMatrix',
    pattern: /import\s+IpamMatrix\s+from\s+['"][^'"]*ipamMatrix['"]/,
  },
  {
    name: 'RoomFloorPlan',
    pattern: /import\s+RoomFloorPlan\s+from\s+['"][^'"]*roomFloorPlan['"]/,
  },
  {
    name: 'RackElevation',
    pattern: /import\s+RackElevation\s+from\s+['"][^'"]*rackElevation['"]/,
  },
];

for (const { name, pattern } of requiredImports) {
  if (!pattern.test(hostSrc)) {
    failures.push(`[ViewCanvasHost.tsx] missing import ${name}`);
  }
}

if (!/<ApplicationResourceOverview[\s\S]*?fillContainer/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] application canvas should fill the hub workspace');
}

if (!/viewType === 'k8s'[\s\S]*?-m-4/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] k8s canvas should fill the hub workspace');
}

if (!/<RoomFloorPlan[\s\S]*?onRackSelect\s*=/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] RoomFloorPlan missing onRackSelect wiring');
}

if (!/onRoomRackDrill/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] missing onRoomRackDrill prop wiring');
}

if (!/highlightRackId/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] missing highlightRackId prop wiring');
}

const pickerPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/views/components/ViewInstancePicker.tsx'
);
const pickerSrc = fs.readFileSync(pickerPath, 'utf8');
if (!/onPopupScroll/.test(pickerSrc)) {
  failures.push('[ViewInstancePicker.tsx] missing instance popup lazy-load scroll');
}
if (!/SEARCH_PAGE_SIZE/.test(pickerSrc)) {
  failures.push('[ViewInstancePicker.tsx] missing paged instance search');
}

const shellPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/views/components/ViewsWorkspaceShell.tsx'
);
const shellSrc = fs.readFileSync(shellPath, 'utf8');
if (!/backToRoom|handleBackToRoom/.test(shellSrc)) {
  failures.push('[ViewsWorkspaceShell.tsx] missing back-to-room control');
}
if (!/HopDepthControl/.test(shellSrc)) {
  failures.push('[ViewsWorkspaceShell.tsx] network hop control missing in hub bar');
}
if (!/networkCenterHop/.test(shellSrc)) {
  failures.push('[ViewsWorkspaceShell.tsx] must pass networkCenterHop into the canvas host');
}
if (!/centerHop=\{networkCenterHop\}/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] NetworkTopo must receive hub-controlled centerHop');
}
if (!/getModelAssociations/.test(shellSrc)) {
  failures.push(
    '[ViewsWorkspaceShell.tsx] network discovery should use getModelAssociations (not N× topo_themes)'
  );
}
if (/getTopoThemes/.test(shellSrc)) {
  failures.push(
    '[ViewsWorkspaceShell.tsx] must not probe every model via getTopoThemes'
  );
}

if (!/export\s+const\s+buildViewsPathPreserving\s*=/.test(urlsSrc)) {
  failures.push('[viewUrls.ts] missing export buildViewsPathPreserving');
}

assert.equal(
  failures.length,
  0,
  '\ncmdb-views-hub-wiring test failed:\n  - ' + failures.join('\n  - ')
);

console.log('cmdb-views-hub-wiring-test: PASS');
