import { cp, mkdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';

const packageRoot = resolve(import.meta.dirname, '..');
const outdir = resolve(packageRoot, 'dist');

await rm(outdir, { force: true, recursive: true });

async function build(
  name: string,
  entrypoint: string,
  external: string[],
  format: 'esm' | 'iife' = 'esm',
) {
  const bundle = await Bun.build({
    bundle: true,
    entrypoints: [resolve(packageRoot, entrypoint)],
    external,
    format,
    minify: false,
    naming: name,
    outdir,
    sourcemap: 'external',
    target: 'browser',
  });
  if (!bundle.success) {
    for (const log of bundle.logs) console.error(log);
    throw new Error(`bklite-rum-sdk bundle ${name} failed`);
  }
}

// NPM entry keeps @grafana/faro-web-sdk external (consumer installs it).
await build('index.js', 'scripts/bundle-entry.ts', ['@grafana/faro-web-sdk']);
// CDN snippets use a classic <script src> plus a global initCoreRum() call.
// ESM would leave `export { ... }` in the file and the snippet would throw.
await build('bklite-rum-sdk.cdn.js', 'scripts/cdn-entry.ts', [], 'iife');
await build('bklite-rum-replay.js', 'scripts/replay-entry.ts', []);

const declarations = Bun.spawnSync({
  cmd: [
    process.execPath,
    'x',
    'tsc',
    '--project',
    resolve(packageRoot, 'tsconfig.build.json'),
  ],
  cwd: packageRoot,
  stderr: 'inherit',
  stdout: 'inherit',
});
if (declarations.exitCode !== 0) {
  throw new Error('bklite-rum-sdk declaration build failed');
}

// Expose the CDN bundles to the web host so generated CDN snippets resolve at
// <public_url>/rum/bklite-rum-sdk.js (and bklite-rum-replay.js when Replay is on).
const webPublicRum = resolve(packageRoot, '../../web/public/rum');
await mkdir(webPublicRum, { recursive: true });
await cp(resolve(outdir, 'bklite-rum-sdk.cdn.js'), resolve(webPublicRum, 'bklite-rum-sdk.js'));
await cp(resolve(outdir, 'bklite-rum-replay.js'), resolve(webPublicRum, 'bklite-rum-replay.js'));
