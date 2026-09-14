import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SOURCE_PATH = resolve(
  process.cwd(),
  'src/app/mlops/components/algorithm-detail/AlgorithmDetail.tsx'
);

const splitTopLevel = (text: string, separator: string): string[] => {
  const parts: string[] = [];
  let current = '';
  let depth = 0;
  let square = 0;
  let curly = 0;
  let quote: string | null = null;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const prev = text[index - 1];
    if (quote) {
      if (char === quote && prev !== '\\') {
        quote = null;
      }
      current += char;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      current += char;
      continue;
    }
    if (char === '(') depth += 1;
    if (char === ')') depth -= 1;
    if (char === '[') square += 1;
    if (char === ']') square -= 1;
    if (char === '{') curly += 1;
    if (char === '}') curly -= 1;
    if (
      char === separator &&
      depth === 0 &&
      square === 0 &&
      curly === 0
    ) {
      parts.push(current);
      current = '';
      continue;
    }
    current += char;
  }
  if (current.trim()) {
    parts.push(current);
  }
  return parts;
};

const extractCallArguments = (source: string, callStart: number): string[] => {
  const openParen = source.indexOf('(', callStart);
  assert.notEqual(openParen, -1, 'hook call is missing "("');

  let depth = 0;
  let quote: string | null = null;
  for (let index = openParen; index < source.length; index += 1) {
    const char = source[index];
    const prev = source[index - 1];
    if (quote) {
      if (char === quote && prev !== '\\') {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      continue;
    }
    if (char === '(') depth += 1;
    if (char === ')') {
      depth -= 1;
      if (depth === 0) {
        return splitTopLevel(source.slice(openParen + 1, index), ',');
      }
    }
  }
  throw new Error('unclosed hook call');
};

const parseIdentList = (depsSource: string | undefined): string[] => {
  if (!depsSource) {
    return [];
  }
  const trimmed = depsSource.trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) {
    return [];
  }
  return trimmed
    .slice(1, -1)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
};

const extractAssignment = (
  source: string,
  ident: string
): {
  hook: 'useMemo' | 'useCallback' | null;
  body: string;
  deps: string[];
} => {
  const pattern = new RegExp(`const ${ident}\\s*=\\s*`);
  const match = pattern.exec(source);
  assert.ok(match, `missing assignment for ${ident}`);
  const start = match.index + match[0].length;
  const next = source.slice(start).trimStart();

  if (next.startsWith('useMemo') || next.startsWith('useCallback')) {
    const hook = next.startsWith('useMemo') ? 'useMemo' : 'useCallback';
    const args = extractCallArguments(source, start);
    return {
      hook,
      body: args[0] || '',
      deps: parseIdentList(args[1]),
    };
  }

  return {
    hook: null,
    body: next,
    deps: [],
  };
};

const extractGetDatasetEffectDeps = (source: string): string[] => {
  const effectPattern = /useEffect\(\(\)\s*=>\s*\{\s*getDataset\(\);\s*\},\s*\[([^\]]*)\]\)/;
  const match = effectPattern.exec(source);
  if (!match) {
    return [];
  }
  return match[1]
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
};

const hasRequiredPaginationDeps = (deps: string[]): boolean =>
  deps.includes('pagination.current') && deps.includes('pagination.pageSize');

const main = () => {
  assert.equal(
    existsSync(SOURCE_PATH),
    true,
    `source file missing: ${SOURCE_PATH}`
  );

  const source = readFileSync(SOURCE_PATH, 'utf8');
  const getDataset = extractAssignment(source, 'getDataset');
  const queryBody = getDataset.body || source;

  assert.match(
    queryBody,
    /page:\s*pagination\.current/,
    '查询必须用 page: pagination.current'
  );
  assert.match(
    queryBody,
    /page_size:\s*pagination\.pageSize/,
    '查询必须用 page_size: pagination.pageSize'
  );

  const staleOnlySearchDeps =
    getDataset.hook === 'useCallback' &&
    getDataset.deps.length === 2 &&
    getDataset.deps[0] === 't' &&
    getDataset.deps[1] === 'searchParams';

  assert.equal(
    staleOnlySearchDeps,
    false,
    `getDataset 的 useCallback 依赖只有 [${getDataset.deps.join(', ')}]，翻页后 effect 重跑仍调用初始闭包`
  );

  const callbackHasPageDeps =
    getDataset.hook === 'useCallback' &&
    hasRequiredPaginationDeps(getDataset.deps) &&
    !getDataset.deps.includes('pagination');

  const queryMovedIntoEffect =
    getDataset.hook !== 'useCallback' &&
    hasRequiredPaginationDeps(extractGetDatasetEffectDeps(source));

  assert.equal(
    callbackHasPageDeps || queryMovedIntoEffect,
    true,
    'getDataset 必须显式依赖 pagination.current 与 pagination.pageSize，或把查询放进依赖完整的 effect；禁止依赖整个 pagination 对象'
  );

  if (getDataset.hook === 'useCallback') {
    assert.equal(
      getDataset.deps.includes('datasetType'),
      true,
      'getDataset 必须显式依赖 datasetType'
    );
    assert.equal(
      getDataset.deps.includes('datasetId'),
      true,
      'getDataset 必须显式依赖 datasetId'
    );
    assert.equal(
      getDataset.deps.includes('getTrainDataByDataset'),
      true,
      'getDataset 必须显式依赖 API getTrainDataByDataset'
    );
  }

  console.log('PASS mlops-dataset-detail-pagination');
};

main();
