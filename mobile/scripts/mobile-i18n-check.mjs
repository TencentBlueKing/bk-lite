import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);
const localeDir = new URL('./src/locales/', projectRoot);
const sourceRoot = new URL('./src/', projectRoot);
const CJK = /[\u4e00-\u9fff]/;

/**
 * 已确认保留、不进入语言包的原文。
 * 新增用户可见中文不要加到这里，应接入 t()。
 */
const keptCopy = new Map([
  ['简体中文', '语言选择器副标题，保留语言自称'],
  ['cc-default_默认', '监控对象默认图标文件名'],
  ['cc-default_默认.svg', '监控对象默认图标文件名'],
  ['未收到有效的 AI 响应', '请求层内部错误，对话界面使用 chat.responseError'],
  ['服务器返回错误', '请求层内部错误，对话界面使用 chat.responseError'],
  ['服务器返回了非预期的响应格式', '请求层内部错误，对话界面使用 chat.responseError'],
]);

function parseJsonValue(text) {
  let index = 0;
  const duplicates = [];

  function skipWhitespace() {
    while (index < text.length && /\s/.test(text[index])) index += 1;
  }

  function fail(message) {
    throw new Error(`${message} at ${index}`);
  }

  function parseString() {
    if (text[index] !== '"') fail('expected string');
    index += 1;
    let value = '';
    while (index < text.length) {
      const char = text[index];
      if (char === '\\') {
        value += text[index + 1] ?? '';
        index += 2;
        continue;
      }
      if (char === '"') {
        index += 1;
        return value;
      }
      value += char;
      index += 1;
    }
    fail('unterminated string');
  }

  function parseLiteral(literal) {
    if (!text.startsWith(literal, index)) fail(`expected ${literal}`);
    index += literal.length;
  }

  function parseNumber() {
    const start = index;
    if (text[index] === '-') index += 1;
    while (index < text.length && /[0-9eE+.-]/.test(text[index])) index += 1;
    if (index === start) fail('expected number');
  }

  function parseValue() {
    skipWhitespace();
    const char = text[index];
    if (char === '{') return parseObject();
    if (char === '[') return parseArray();
    if (char === '"') return parseString();
    if (text.startsWith('true', index)) return parseLiteral('true');
    if (text.startsWith('false', index)) return parseLiteral('false');
    if (text.startsWith('null', index)) return parseLiteral('null');
    if (char === '-' || (char >= '0' && char <= '9')) return parseNumber();
    fail(`unexpected ${char ?? 'eof'}`);
  }

  function parseObject() {
    const seen = new Set();
    index += 1;
    skipWhitespace();
    if (text[index] === '}') {
      index += 1;
      return;
    }
    while (index < text.length) {
      skipWhitespace();
      const key = parseString();
      if (seen.has(key)) duplicates.push(key);
      seen.add(key);
      skipWhitespace();
      if (text[index] !== ':') fail('expected colon');
      index += 1;
      parseValue();
      skipWhitespace();
      if (text[index] === ',') {
        index += 1;
        continue;
      }
      if (text[index] === '}') {
        index += 1;
        return;
      }
      fail('expected comma or closing brace');
    }
    fail('unterminated object');
  }

  function parseArray() {
    index += 1;
    skipWhitespace();
    if (text[index] === ']') {
      index += 1;
      return;
    }
    while (index < text.length) {
      parseValue();
      skipWhitespace();
      if (text[index] === ',') {
        index += 1;
        continue;
      }
      if (text[index] === ']') {
        index += 1;
        return;
      }
      fail('expected comma or closing bracket');
    }
    fail('unterminated array');
  }

  parseValue();
  skipWhitespace();
  if (index !== text.length) fail('trailing content');
  return duplicates;
}

function flattenMessages(value, prefix = '', output = {}) {
  if (typeof value === 'string') {
    output[prefix] = value;
    return output;
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${prefix || '<root>'} 不是字符串或对象`);
  }
  for (const [key, child] of Object.entries(value)) {
    const next = prefix ? `${prefix}.${key}` : key;
    flattenMessages(child, next, output);
  }
  return output;
}

function placeholderNames(message) {
  const names = [];
  const pattern = /\{([A-Za-z_][\w]*)\s*(?:,|\})/g;
  for (const match of message.matchAll(pattern)) {
    names.push(match[1]);
  }
  return names.sort();
}

async function readLocale(name) {
  const fileUrl = new URL(name, localeDir);
  const text = await readFile(fileUrl, 'utf8');
  const duplicates = parseJsonValue(text);
  const messages = flattenMessages(JSON.parse(text));
  return { name, duplicates, messages };
}

async function sourceFiles() {
  const files = [];
  async function walk(directoryUrl) {
    const entries = await readdir(directoryUrl, { withFileTypes: true });
    for (const entry of entries) {
      const next = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, directoryUrl);
      if (entry.isDirectory()) {
        if (entry.name === 'locales') continue;
        await walk(next);
        continue;
      }
      if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) files.push(next);
    }
  }
  await walk(sourceRoot);
  return files;
}

function lineOf(sourceFile, node) {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
}

function isConsoleCall(node) {
  let current = node.parent;
  while (current) {
    if (ts.isCallExpression(current)) {
      const expression = current.expression;
      if (
        ts.isPropertyAccessExpression(expression)
        && ts.isIdentifier(expression.expression)
        && expression.expression.text === 'console'
      ) {
        return true;
      }
    }
    current = current.parent;
  }
  return false;
}

function recordCopy(findings, filePath, line, text) {
  const trimmed = text.trim();
  if (!CJK.test(trimmed) || keptCopy.has(trimmed)) return;
  findings.push(`${filePath}:${line} ${trimmed}`);
}

test('重复 key 会被解析器发现', () => {
  assert.deepEqual(parseJsonValue('{"a":"1","a":"2"}'), ['a']);
  assert.deepEqual(parseJsonValue('{"a":{"b":"1","b":"2"}}'), ['b']);
  assert.deepEqual(parseJsonValue('{"a":"1","b":"2"}'), []);
});

test('移动端中英文语言包对称且占位符一致', async () => {
  const zh = await readLocale('zh.json');
  const en = await readLocale('en.json');
  assert.deepEqual(zh.duplicates, [], `zh.json 有重复 key: ${zh.duplicates.join(', ')}`);
  assert.deepEqual(en.duplicates, [], `en.json 有重复 key: ${en.duplicates.join(', ')}`);

  const zhKeys = Object.keys(zh.messages).sort();
  const enKeys = Object.keys(en.messages).sort();
  const missingEn = zhKeys.filter((key) => !(key in en.messages));
  const missingZh = enKeys.filter((key) => !(key in zh.messages));
  assert.deepEqual(missingEn, [], `en.json 缺少 ${missingEn.join(', ')}`);
  assert.deepEqual(missingZh, [], `zh.json 缺少 ${missingZh.join(', ')}`);

  const placeholderMismatches = zhKeys.filter((key) => (
    placeholderNames(zh.messages[key]).join('|') !== placeholderNames(en.messages[key]).join('|')
  ));
  assert.deepEqual(placeholderMismatches, [], `占位符不一致: ${placeholderMismatches.join(', ')}`);
});

test('静态翻译引用存在，用户可见中文只保留已确认项', async () => {
  const zh = await readLocale('zh.json');
  const roots = new Set(Object.keys(JSON.parse(await readFile(new URL('zh.json', localeDir), 'utf8'))));
  const rootPattern = new RegExp(`^(${[...roots].join('|')})\\.[A-Za-z_]`);
  const missingKeys = [];
  const hardcoded = [];

  for (const fileUrl of await sourceFiles()) {
    const text = await readFile(fileUrl, 'utf8');
    const filePath = path.relative(fileURLToPath(projectRoot), fileURLToPath(fileUrl));
    const sourceFile = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

    function visit(node) {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't') {
        const keyNode = node.arguments[0];
        if (keyNode && (ts.isStringLiteral(keyNode) || ts.isNoSubstitutionTemplateLiteral(keyNode))) {
          if (!(keyNode.text in zh.messages)) missingKeys.push(`${filePath}:${lineOf(sourceFile, keyNode)} ${keyNode.text}`);
        }
      }

      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !isConsoleCall(node)) {
        recordCopy(hardcoded, filePath, lineOf(sourceFile, node), node.text);
        if (rootPattern.test(node.text) && !(node.text in zh.messages)) {
          missingKeys.push(`${filePath}:${lineOf(sourceFile, node)} ${node.text}`);
        }
      }

      if (ts.isTemplateExpression(node) && !isConsoleCall(node)) {
        recordCopy(hardcoded, filePath, lineOf(sourceFile, node), node.head.text);
        for (const span of node.templateSpans) recordCopy(hardcoded, filePath, lineOf(sourceFile, span.literal), span.literal.text);
      }

      if (ts.isJsxText(node)) recordCopy(hardcoded, filePath, lineOf(sourceFile, node), node.getText(sourceFile));
      ts.forEachChild(node, visit);
    }

    visit(sourceFile);
  }

  assert.deepEqual(missingKeys, [], `缺少语言 key:\n${missingKeys.join('\n')}`);
  assert.deepEqual(hardcoded, [], `未确认的用户可见中文:\n${hardcoded.join('\n')}`);
});
