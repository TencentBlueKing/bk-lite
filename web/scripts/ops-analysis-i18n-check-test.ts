/**
 * ops-analysis app-level i18n static gate (#4340 AC4).
 *
 * Checks:
 * - en/zh locale JSON parse + duplicate keys
 * - key symmetry
 * - ICU/placeholder name sets per key
 * - static t('...') keys exist in ops-analysis and/or shared locales
 * - remaining hardcoded CJK outside confirmed keeps / DEFERs
 *
 * Run: pnpm test:ops-analysis-i18n
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import ts from 'typescript';

type Messages = Record<string, unknown>;

const root = path.resolve(process.cwd());
const appDir = 'src/app/ops-analysis';
const localeDir = path.join(appDir, 'locales');
const CJK = /[\u4e00-\u9fff]/;

/**
 * 已确认保留、不进入语言包的原文（#4340 DEFER / 非用户文案）。
 * 新增用户可见中文不要加到这里，应接入 t()。
 */
const keptCopy = new Map<string, string>([
  ['无数据', '#4340 DEFER：topology registerNode empty caption'],
  ['仪表盘编辑状态', '搭盘协议标题，后端按这个标记读取编辑快照'],
  ['仪表盘编辑配置过长，本轮无法安全搭盘。请先减少组件后再描述调整。', '搭盘协议正文，后端按「无法安全搭盘」停止套用'],
  // 时钟预设的存储 id 与画面字面量，规格要求原样展示，不随界面语言改写。
  ['YYYY年M月D日', 'screen clock format id'],
  ['M月D日 HH:mm', 'screen clock format id'],
  ['年', 'screen clock glyph'],
  ['月', 'screen clock glyph'],
  ['日', 'screen clock glyph'],
  ['一', 'screen clock glyph'],
  ['二', 'screen clock glyph'],
  ['三', 'screen clock glyph'],
  ['四', 'screen clock glyph'],
  ['五', 'screen clock glyph'],
  ['六', 'screen clock glyph'],
  ['星期', 'screen clock glyph'],
]);

/** 整文件跳过：Storybook / pilot / 测试夹具。 */
const skipPath = (relativePath: string) => {
  if (relativePath.includes(`${path.sep}__tests__${path.sep}`)) return true;
  if (relativePath.includes(`${path.sep}locales${path.sep}`)) return true;
  if (/\.test\.(ts|tsx)$/.test(relativePath)) return true;
  if (/\.stories\.(ts|tsx)$/.test(relativePath)) return true;
  if (/\.pilot\.ts$/.test(relativePath)) return true;
  return false;
};

const read = (relativePath: string) => fs.readFileSync(path.join(root, relativePath), 'utf8');

function parseJsonValue(text: string): string[] {
  let index = 0;
  const duplicates: string[] = [];

  const skipWhitespace = () => {
    while (index < text.length && /\s/.test(text[index]!)) index += 1;
  };
  const fail = (message: string): never => {
    throw new Error(`${message} at ${index}`);
  };
  const parseString = () => {
    if (text[index] !== '"') fail('expected string');
    index += 1;
    let value = '';
    while (index < text.length) {
      const char = text[index]!;
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
  };
  const parseLiteral = (literal: string) => {
    if (!text.startsWith(literal, index)) fail(`expected ${literal}`);
    index += literal.length;
  };
  const parseNumber = () => {
    const start = index;
    if (text[index] === '-') index += 1;
    while (index < text.length && /[0-9eE+.-]/.test(text[index]!)) index += 1;
    if (index === start) fail('expected number');
  };

  const parseValue = (): void => {
    skipWhitespace();
    const char = text[index];
    if (char === '{') return parseObject();
    if (char === '[') return parseArray();
    if (char === '"') {
      parseString();
      return;
    }
    if (text.startsWith('true', index)) return parseLiteral('true');
    if (text.startsWith('false', index)) return parseLiteral('false');
    if (text.startsWith('null', index)) return parseLiteral('null');
    if (char === '-' || (char !== undefined && char >= '0' && char <= '9')) return parseNumber();
    fail(`unexpected ${char ?? 'eof'}`);
  };

  const parseObject = () => {
    const seen = new Set<string>();
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
  };

  const parseArray = () => {
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
  };

  parseValue();
  skipWhitespace();
  if (index !== text.length) fail('trailing content');
  return duplicates;
}

const flatten = (
  value: Messages,
  prefix = '',
  result: Record<string, string> = {},
): Record<string, string> => {
  for (const [key, item] of Object.entries(value)) {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (typeof item === 'string') result[nextKey] = item;
    else if (item && typeof item === 'object' && !Array.isArray(item)) {
      flatten(item as Messages, nextKey, result);
    } else {
      throw new Error(`${nextKey} 不是字符串或对象`);
    }
  }
  return result;
};

const placeholderNames = (message: string) => {
  const names: string[] = [];
  const pattern = /\{([A-Za-z_][\w]*)\s*(?:,|\})/g;
  for (const match of message.matchAll(pattern)) {
    names.push(match[1]!);
  }
  return names.sort();
};

const readLocale = (name: 'en' | 'zh') => {
  const relativePath = path.join(localeDir, `${name}.json`);
  const text = read(relativePath);
  const duplicates = parseJsonValue(text);
  const messages = flatten(JSON.parse(text) as Messages);
  return { name, relativePath, duplicates, messages };
};

const collectSourcePaths = (directory: string): string[] =>
  fs.readdirSync(path.join(root, directory), { withFileTypes: true }).flatMap((entry) => {
    const relativePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'locales' || entry.name === '__tests__') {
        return [];
      }
      return collectSourcePaths(relativePath);
    }
    if (!/\.(?:ts|tsx)$/.test(entry.name) || /\.test\.(?:ts|tsx)$/.test(entry.name)) return [];
    if (skipPath(relativePath)) return [];
    return [relativePath];
  });

const lineOf = (sourceFile: ts.SourceFile, node: ts.Node) =>
  sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

const isConsoleCall = (node: ts.Node) => {
  let current: ts.Node | undefined = node.parent;
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
};

const isI18nFallbackContext = (node: ts.Node) => {
  let current: ts.Node | undefined = node;
  while (current) {
    const parent = current.parent;
    if (!parent) break;
    if (ts.isCallExpression(parent) && parent.arguments.includes(current as ts.Expression)) {
      const expression = parent.expression;
      if (ts.isIdentifier(expression) && (expression.text === 't' || expression.text === 'unitLabel')) {
        return true;
      }
    }
    if (
      ts.isPropertyAssignment(parent)
      && current === parent.initializer
      && ts.isIdentifier(parent.name)
      && ['fallback', 'defaultMessage', 'default'].includes(parent.name.text)
    ) {
      return true;
    }
    if (ts.isCallExpression(parent) && ts.isIdentifier(parent.expression) && parent.expression.text === 't') {
      return true;
    }
    current = parent;
  }
  return false;
};

test('重复 key 会被严格 JSON 解析器发现', () => {
  assert.deepEqual(parseJsonValue('{"a":"1","a":"2"}'), ['a']);
  assert.deepEqual(parseJsonValue('{"a":{"b":"1","b":"2"}}'), ['b']);
  assert.deepEqual(parseJsonValue('{"a":"1","b":"2"}'), []);
});

test('ops-analysis 中英文语言包对称且占位符一致', () => {
  const zh = readLocale('zh');
  const en = readLocale('en');
  assert.deepEqual(zh.duplicates, [], `zh.json 有重复 key: ${zh.duplicates.join(', ')}`);
  assert.deepEqual(en.duplicates, [], `en.json 有重复 key: ${en.duplicates.join(', ')}`);

  const zhKeys = Object.keys(zh.messages).sort();
  const enKeys = Object.keys(en.messages).sort();
  const missingEn = zhKeys.filter((key) => !(key in en.messages));
  const missingZh = enKeys.filter((key) => !(key in zh.messages));
  assert.deepEqual(missingEn, [], `en.json 缺少 ${missingEn.join(', ')}`);
  assert.deepEqual(missingZh, [], `zh.json 缺少 ${missingZh.join(', ')}`);

  const placeholderMismatches = zhKeys.filter(
    (key) => placeholderNames(zh.messages[key]!).join('|') !== placeholderNames(en.messages[key]!).join('|'),
  );
  assert.deepEqual(placeholderMismatches, [], `占位符不一致: ${placeholderMismatches.join(', ')}`);
});

test('静态 t() 引用存在，用户可见中文只保留已确认项', () => {
  const zh = readLocale('zh');
  const commonZh = flatten(JSON.parse(read('src/locales/zh.json')) as Messages);
  const commonEn = flatten(JSON.parse(read('src/locales/en.json')) as Messages);
  const knownKeys = new Set([
    ...Object.keys(zh.messages),
    ...Object.keys(commonZh),
    ...Object.keys(commonEn),
  ]);

  const missingKeys: string[] = [];
  const hardcoded: string[] = [];

  for (const sourcePath of collectSourcePaths(appDir)) {
    const text = read(sourcePath);
    const sourceFile = ts.createSourceFile(
      sourcePath,
      text,
      ts.ScriptTarget.Latest,
      true,
      sourcePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
    );

    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't') {
        const keyNode = node.arguments[0];
        if (keyNode && (ts.isStringLiteral(keyNode) || ts.isNoSubstitutionTemplateLiteral(keyNode))) {
          if (!knownKeys.has(keyNode.text)) {
            missingKeys.push(`${sourcePath}:${lineOf(sourceFile, keyNode)} ${keyNode.text}`);
          }
        }
      }

      const recordCopy = (raw: string, at: ts.Node) => {
        const trimmed = raw.trim();
        if (!CJK.test(trimmed) || keptCopy.has(trimmed)) return;
        if (isConsoleCall(at) || isI18nFallbackContext(at)) return;
        hardcoded.push(`${sourcePath}:${lineOf(sourceFile, at)} ${trimmed}`);
      };

      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !isConsoleCall(node)) {
        recordCopy(node.text, node);
      }
      if (ts.isTemplateExpression(node) && !isConsoleCall(node)) {
        recordCopy(node.head.text, node);
        for (const span of node.templateSpans) {
          recordCopy(span.literal.text, span.literal);
        }
      }
      if (ts.isJsxText(node)) {
        recordCopy(node.getText(sourceFile), node);
      }

      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
  }

  assert.deepEqual(missingKeys, [], `缺少语言 key:\n${missingKeys.join('\n')}`);
  assert.deepEqual(hardcoded, [], `未确认的用户可见中文:\n${hardcoded.join('\n')}`);
});
