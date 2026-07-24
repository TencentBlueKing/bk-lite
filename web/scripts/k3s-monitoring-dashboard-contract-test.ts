import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (relativePath: string) =>
  fs.readFileSync(path.join(root, relativePath), 'utf8');
const walk = (directory: string): string[] =>
  fs.readdirSync(path.join(root, directory), { withFileTypes: true }).flatMap(
    (entry) => {
      const relativePath = path.join(directory, entry.name);
      return entry.isDirectory() ? walk(relativePath) : [relativePath];
    }
  );

const monitorConfig = read('src/app/monitor/hooks/integration/index.tsx');
const registry = read('src/app/monitor/dashboards/registry.ts');
const objectFiles = [
  'src/app/monitor/hooks/integration/objects/k3s/cluster.tsx',
  'src/app/monitor/hooks/integration/objects/k3s/node.tsx',
  'src/app/monitor/hooks/integration/objects/k3s/pod.tsx',
];
const objectSource = objectFiles.map(read).join('\n');
const dashboardFiles = [
  ...walk('src/app/monitor/dashboards/objects/k3s-cluster'),
  ...walk('src/app/monitor/dashboards/objects/k3s-node'),
  ...walk('src/app/monitor/dashboards/objects/k3s-pod'),
].filter((file) => /\.(ts|tsx)$/.test(file));
const dashboardSource = dashboardFiles.map(read).join('\n');

assert.match(monitorConfig, /K3SCluster:\s*k3sClusterConfig/);
assert.match(monitorConfig, /K3SNode:\s*k3sNodeConfig/);
assert.match(monitorConfig, /K3SPod:\s*k3sPodConfig/);
assert.match(objectSource, /instance_type:\s*'k3s'/);
assert.match(objectSource, /collectTypes:\s*\{\s*K3S:\s*'k3s'/);

for (const [routeKey, objectName] of [
  ['k3s-cluster', 'K3SCluster'],
  ['k3s-node', 'K3SNode'],
  ['k3s-pod', 'K3SPod'],
]) {
  assert.match(
    registry,
    new RegExp(`key: '${routeKey}'[\\s\\S]*objectName: '${objectName}'`)
  );
}

assert.doesNotMatch(dashboardSource, /from ['"][^'"]*k8s-/);
assert.doesNotMatch(dashboardSource, /instance_type=['"]k8s['"]/);
assert.match(dashboardSource, /instance_type=['"]k3s['"]/);
assert.doesNotMatch(objectSource, /instance_type:\s*'k8s'/);

console.log('K3S dashboard contract passed');
