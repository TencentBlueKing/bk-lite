import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SOURCE_PATH = resolve(
  process.cwd(),
  'src/app/mlops/components/annotation/objectDetection.tsx'
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

const main = () => {
  assert.equal(
    existsSync(SOURCE_PATH),
    true,
    `source file missing: ${SOURCE_PATH}`
  );

  const source = readFileSync(SOURCE_PATH, 'utf8');
  const toolbarRight = extractAssignment(source, 'toolbarRight');
  const saveResult = extractAssignment(source, 'saveResult');
  const getObjectTrainDataInfo = extractAssignment(
    source,
    'getObjectTrainDataInfo'
  );

  const toolbarDepsKey = toolbarRight.deps.join(',');
  assert.notEqual(
    toolbarRight.hook === 'useMemo' && toolbarDepsKey === 't',
    true,
    'toolbarRight useMemo 只依赖 [t]，保存按钮会钉在首次 trainData=[] / fileId 闭包上'
  );

  const saveReadsCurrentTrainData =
    /num_images:\s*trainData\.length/.test(saveResult.body) ||
    /num_images:\s*trainData\.length/.test(source);
  assert.equal(
    saveReadsCurrentTrainData,
    true,
    'saveResult 必须用当前 trainData.length 作为 num_images'
  );
  assert.match(
    saveResult.body,
    /updateObjectDetectionTrainData\(\s*fileId\s*,/,
    'saveResult 必须把当前 fileId 传给更新接口'
  );

  const saveHasCurrentTrainDataCallback =
    saveResult.hook === 'useCallback' &&
    saveResult.deps.includes('trainData');
  const toolbarMemoCancelled = toolbarRight.hook !== 'useMemo';
  const toolbarDependsOnSaveCallback =
    toolbarRight.hook === 'useMemo' &&
    toolbarRight.deps.includes('saveResult') &&
    saveHasCurrentTrainDataCallback;

  assert.equal(
    toolbarMemoCancelled || toolbarDependsOnSaveCallback,
    true,
    'saveResult 必须是依赖含 trainData 的 useCallback，且纳入 toolbarRight；或取消该工具栏 memo'
  );

  if (toolbarRight.hook === 'useMemo') {
    assert.equal(
      toolbarRight.deps.includes('getObjectTrainDataInfo') ||
        getObjectTrainDataInfo.hook === 'useCallback',
      true,
      'toolbarRight 仍 memo 时，getObjectTrainDataInfo 也必须是稳定且可拿到当前 fileId 的回调'
    );
  }

  console.log('PASS mlops-object-detection-save-stale');
};

main();
