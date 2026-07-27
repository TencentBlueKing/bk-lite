import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const workspace = path.resolve(process.cwd(), '..');
const read = (relativePath: string) =>
  fs.readFileSync(path.join(workspace, relativePath), 'utf8');
const walk = (relativeDirectory: string): string[] =>
  fs
    .readdirSync(path.join(workspace, relativeDirectory), { withFileTypes: true })
    .flatMap((entry) => {
      const relativePath = path.join(relativeDirectory, entry.name);
      return entry.isDirectory() ? walk(relativePath) : [relativePath];
    });
const readTree = (relativeDirectory: string) =>
  walk(relativeDirectory)
    .filter((file) => /\.(py|sh|ts|tsx|yaml)$/.test(file))
    .map(read)
    .join('\n');

const backend = [
  read('server/apps/monitor/services/k3s_onboarding.py'),
  read('server/apps/monitor/views/k3s_onboarding.py'),
].join('\n');
const renderer = read('agents/webhookd/infra/k3s.sh');
const manifest = read('agents/webhookd/bk-lite-k3s-metric-collector.yaml');
const frontend = [
  readTree(
    'web/src/app/monitor/(pages)/integration/list/detail/configure/k3s'
  ),
  readTree('web/src/app/monitor/hooks/integration/objects/k3s'),
  readTree('web/src/app/monitor/dashboards/objects/k3s-cluster'),
  readTree('web/src/app/monitor/dashboards/objects/k3s-node'),
  readTree('web/src/app/monitor/dashboards/objects/k3s-pod'),
].join('\n');

assert.doesNotMatch(backend, /\b(?:InfraService|ManualCollectService)\b/);
assert.doesNotMatch(renderer, /kubernetes\.sh|bk-lite-k8s/);
assert.doesNotMatch(frontend, /configure\/k8s|dashboards\/objects\/k8s-/);
assert.doesNotMatch(frontend, /instance_type:\s*['"]k8s['"]/);
assert.match(frontend, /instance_type:\s*['"]k3s['"]/);
assert.doesNotMatch(manifest, /\bbk-lite-collector\b|bk-lite-k8s/);
assert.match(manifest, /\bbk-lite-k3s-collector\b/);

console.log('K3S isolation contract passed');
