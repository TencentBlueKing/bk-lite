import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Runtime code is bundled by esbuild/Vite. Keep the public declarations equally
// self-contained instead of publishing a dependency on a private checkout path.
const sdkRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const packageRoot = process.cwd();
const require = createRequire(path.join(packageRoot, 'package.json'));
const contentRoot = path.dirname(path.dirname(require.resolve('@bk-lite/chat-content/core')));
const dist = path.join(packageRoot, 'dist');
const contentTypes = path.join(dist, 'chat-content');
rmSync(contentTypes, { recursive: true, force: true });
execFileSync(path.join(sdkRoot, 'node_modules/.bin/tsc'), [
  '-p', path.join(contentRoot, 'tsconfig.json'),
  '--noEmit', 'false', '--declaration', '--emitDeclarationOnly',
  '--rootDir', path.join(contentRoot, 'src'), '--outDir', contentTypes,
], { stdio: 'inherit' });

function localizeDeclarations(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      localizeDeclarations(file);
    } else if (entry.name.endsWith('.d.ts')) {
      const source = readFileSync(file, 'utf8');
      const next = source
        .replace(/^import ['"]@bk-lite\/chat-content\/style\.css['"];?\s*$/gm, '')
        .replace(/(['"])@bk-lite\/chat-content\/([^'"]+)\1/g, (_match, quote, module) => {
          let relative = path.relative(path.dirname(file), path.join(contentTypes, module)).split(path.sep).join('/');
          if (!relative.startsWith('.')) relative = `./${relative}`;
          return `${quote}${relative}${quote}`;
        });
      if (next !== source) writeFileSync(file, next);
    }
  }
}
localizeDeclarations(dist);
