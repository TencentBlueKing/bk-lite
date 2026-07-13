import fs from 'node:fs';
import path from 'node:path';

const graphExplorerPath = path.join(
  process.cwd(),
  'src/app/opspilot/components/wiki/GraphExplorer.tsx'
);
const graphCanvasPath = path.join(
  process.cwd(),
  'src/app/opspilot/components/wiki/GraphCanvas.tsx'
);

const explorer = fs.readFileSync(graphExplorerPath, 'utf8');
const canvas = fs.readFileSync(graphCanvasPath, 'utf8');
const sources = { canvas, explorer };

const expectations: Array<[keyof typeof sources, RegExp, string]> = [
  ['canvas', /resizeToFit:\s*\(\)\s*=>\s*void/, 'GraphCanvasHandle should expose resizeToFit for container size changes.'],
  ['canvas', /resizeToFit:\s*\(\)\s*=>\s*\{[\s\S]*?fitGraphToContainer/, 'GraphCanvas resizeToFit should resize and fit the graph.'],
  ['explorer', /\[fullscreen,\s*shownNodes\.length\]/, 'GraphExplorer should react when fullscreen changes.'],
  ['explorer', /canvasRef\.current\?\.resizeToFit\(\)/, 'GraphExplorer should resize and fit the canvas after entering fullscreen.'],
];

const failures = expectations
  .filter(([sourceKey, pattern]) => !pattern.test(sources[sourceKey]))
  .map(([, , message]) => message);

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'));
  process.exit(1);
}

console.log('wiki graph fullscreen resize behavior OK');
