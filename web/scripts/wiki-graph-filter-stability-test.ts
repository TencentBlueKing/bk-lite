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

const expectations: Array<[string, RegExp, string]> = [
  ['canvas', /visibleNodeIds:\s*Set<string>/, 'GraphCanvas should accept visible node ids instead of rebuilding from filtered nodes.'],
  ['canvas', /setElementVisibility\([\s\S]*?\)/, 'GraphCanvas should hide/show elements using G6 visibility APIs.'],
  ['canvas', /\}, \[visibleNodeIdsKey,\s*visibleEdgeIdsKey\]\);/, 'Visibility changes should be handled in a dedicated effect.'],
  ['explorer', /nodes=\{graph\.nodes\}/, 'GraphExplorer should pass the full node set to GraphCanvas.'],
  ['explorer', /edges=\{graph\.edges\}/, 'GraphExplorer should pass the full edge set to GraphCanvas.'],
  ['explorer', /visibleNodeIds=\{shownNodeIds\}/, 'GraphExplorer should pass filtered visibility separately.'],
  ['explorer', /visibleEdgeIds=\{shownEdgeIds\}/, 'GraphExplorer should pass filtered edge visibility separately.'],
];

const sourceByName: Record<string, string> = { canvas, explorer };
const failures = expectations
  .filter(([sourceName, pattern]) => !pattern.test(sourceByName[sourceName]))
  .map(([, , message]) => message);

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'));
  process.exit(1);
}

console.log('wiki graph filter stability behavior OK');
