import fs from 'node:fs';
import path from 'node:path';

const pagePath = path.resolve(
  'src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx'
);
const source = fs.readFileSync(pagePath, 'utf8');
const pageDir = path.dirname(pagePath);

const importPattern = /import\s+(?:type\s+)?(?:[\w*{}\s,]+)\s+from\s+['"](\.[^'"]+)['"]/g;
const missingImports = [];

for (const match of source.matchAll(importPattern)) {
  const request = match[1];
  const resolvedBase = path.resolve(pageDir, request);
  const candidates = [
    resolvedBase,
    `${resolvedBase}.ts`,
    `${resolvedBase}.tsx`,
    `${resolvedBase}.js`,
    `${resolvedBase}.jsx`,
    path.join(resolvedBase, 'index.ts'),
    path.join(resolvedBase, 'index.tsx'),
  ];

  if (!candidates.some((candidate) => fs.existsSync(candidate))) {
    missingImports.push(request);
  }
}

if (missingImports.length > 0) {
  throw new Error(`Missing relationships imports: ${missingImports.join(', ')}`);
}

if (source.includes('<IpamMatrix') && !source.includes('import IpamMatrix')) {
  throw new Error('IpamMatrix is rendered without an import');
}

console.log('cmdb relationships imports test passed');
