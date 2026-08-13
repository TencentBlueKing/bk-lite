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

if (!/<RoomFloorPlan[\s\S]*?onRackSelect\s*=/.test(hostSrc)) {
  failures.push('[ViewCanvasHost.tsx] RoomFloorPlan missing onRackSelect wiring');
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
