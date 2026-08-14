import { spawnSync } from 'node:child_process';

export const workspaces = ['@webchat/core', '@webchat/ui'];

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', stdio: 'pipe', ...options });
  return { ...result, stdout: result.stdout ?? '', stderr: result.stderr ?? '' };
}

function packageField(workspace, field, runner) {
  const result = runner('npm', ['pkg', 'get', field, '--workspace', workspace]);
  if (result.status !== 0) throw new Error(result.stderr || `cannot read ${field} for ${workspace}`);
  return Object.values(JSON.parse(result.stdout))[0];
}

function published(name, version, runner) {
  const result = runner('npm', ['view', `${name}@${version}`, 'version', '--json']);
  if (result.status === 0) return true;
  if (/E404|not found/i.test(result.stderr)) return false;
  throw new Error(result.stderr || `cannot query ${name}@${version}`);
}

export function publishWorkspaces({ runner = run } = {}) {
  for (const workspace of workspaces) {
    const name = packageField(workspace, 'name', runner);
    const version = packageField(workspace, 'version', runner);
    if (published(name, version, runner)) continue;

    const publish = runner('npm', ['publish', '--workspace', workspace]);
    if (publish.status === 0 || published(name, version, runner)) continue;
    throw new Error(publish.stderr || `cannot publish ${name}@${version}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) publishWorkspaces();
