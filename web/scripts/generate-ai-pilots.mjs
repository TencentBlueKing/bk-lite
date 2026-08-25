#!/usr/bin/env node
// Scan web/src/app for *.pilot.ts and write pilots.generated.ts.
// Fail-safe: any error writes an empty list and exits 0.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildPilotsManifestSource,
  emptyManifest,
  walkPilots,
  writeIfChanged,
} from './generate-ai-pilots-lib.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, '..');
const appRoot = path.join(webRoot, 'src', 'app');
const outFile = path.join(webRoot, 'src', 'components', 'ai-page-context', 'pilots.generated.ts');

export { buildPilotsManifestSource, pathnamePrefixFromPilotFile } from './generate-ai-pilots-lib.mjs';

export const generateAiPilots = ({ appDir = appRoot, output = outFile, root = webRoot } = {}) => {
  try {
    const files = walkPilots(appDir);
    const source = buildPilotsManifestSource(files, root);
    const changed = writeIfChanged(output, source);
    return { ok: true, count: files.length, changed, output };
  } catch (error) {
    console.warn('[generate-ai-pilots] failed, writing empty manifest:', error);
    writeIfChanged(output, emptyManifest());
    return { ok: false, count: 0, changed: true, output, error };
  }
};

if (process.argv[1] === __filename) {
  const result = generateAiPilots();
  if (result.ok) {
    console.log(`  ✓ ai-pilots: ${result.count} file(s)${result.changed ? ' (updated)' : ' (unchanged)'}`);
  }
  process.exitCode = 0;
}
