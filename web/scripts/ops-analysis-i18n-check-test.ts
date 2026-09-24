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
  // 大屏日历 classNames：星期缩写协议字面量
  ['日', '#4340 DEFER：screen classNames 星期缩写'],
  ['一', '#4340 DEFER：screen classNames 星期缩写'],
  ['二', '#4340 DEFER：screen classNames 星期缩写'],
  ['三', '#4340 DEFER：screen classNames 星期缩写'],
  ['四', '#4340 DEFER：screen classNames 星期缩写'],
  ['五', '#4340 DEFER：screen classNames 星期缩写'],
  ['六', '#4340 DEFER：screen classNames 星期缩写'],
  ['周', '#4340 DEFER：screen classNames 周前缀'],

  // application3d 墙面切换 / 架构节点标签（本轮不迁）
  ['横向滑入', '#4340 DEFER：application3d wall transition'],
  ['淡入淡出', '#4340 DEFER：application3d wall transition'],
  ['卡片翻转', '#4340 DEFER：application3d wall transition'],
  ['直接切换', '#4340 DEFER：application3d wall transition'],
  ['主机', '#4340 DEFER：application3d / topology fixture labels'],
  ['应用', '#4340 DEFER：application3d architecture label'],

  // 关系拓扑边类型枚举展示（协议侧保留）
  ['属于', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['组成', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['运行于', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['安装于', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['包含', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['关联', '#4340 DEFER：relatedTopology graphModel edge type'],
  ['交换机', '#4340 DEFER：relatedTopology story/fixture label'],
  ['连接', '#4340 DEFER：relatedTopology story/fixture label'],
  ['暂无关联', '#4340 DEFER：relatedTopology empty label'],

  // Prometheus 表单字段中文（operateModal 探测字段名，后续批次再迁）
  ['查询类型', '#4340 DEFER：datasource operateModalUtils field label'],
  ['时间范围', '#4340 DEFER：datasource operateModalUtils field label'],
  ['最大序列数', '#4340 DEFER：datasource operateModalUtils field label'],

  // 表格/事件表配置与校验（候选硬编码，本轮 keep）
  ['请先配置展示字段', '#4340 DEFER：event table empty hint'],
  ['字段 key 不能重复', '#4340 DEFER：widgetConfig table column validation'],
  ['请至少保留一列可见', '#4340 DEFER：widgetConfig table column validation'],
  ['未探测到可用字段', '#4340 DEFER：useTableConfig probe empty'],
  ['将基于当前数据源和参数重新探测并恢复默认列，同时保留已有自定义列', '#4340 DEFER：tableSettingsSection reprobe tip'],
  ['重新探测列', '#4340 DEFER：tableSettingsSection reprobe action'],

  // 阈值校验片段（runtime template）
  ['第', '#4340 DEFER：threshold index fragment'],
  ['个阈值的颜色格式无效', '#4340 DEFER：threshold validation fragment'],
  ['个阈值的数值无效', '#4340 DEFER：threshold validation fragment'],

  // 关系拓扑 / 报表 / 取数校验（候选硬编码）
  ['数据结构不符：关系拓扑期望 nodes 与 edges 数组', '#4340 DEFER：topologyMapData contract'],
  ['关系拓扑第', '#4340 DEFER：topologyMapData index fragment'],
  ['个节点格式错误', '#4340 DEFER：topologyMapData fragment'],
  ['个节点缺少有效 identity 或展示字段', '#4340 DEFER：topologyMapData fragment'],
  ['关系拓扑节点 id 重复：', '#4340 DEFER：topologyMapData fragment'],
  ['关系拓扑节点', '#4340 DEFER：topologyMapData fragment'],
  ['的 alert_count 必须是非负整数', '#4340 DEFER：topologyMapData fragment'],
  ['的 alert_level 必须是字符串', '#4340 DEFER：topologyMapData fragment'],
  ['条边格式错误', '#4340 DEFER：topologyMapData fragment'],
  ['条边的 source 或 target 无效', '#4340 DEFER：topologyMapData fragment'],
  ['条边的 line_style 无效', '#4340 DEFER：topologyMapData fragment'],
  ['条边的 connection_type 无效', '#4340 DEFER：topologyMapData fragment'],
  ['关系拓扑 source + target 重复：', '#4340 DEFER：topologyMapData fragment'],
  ['报表组件 ID 不能重复', '#4340 DEFER：reportBuilder validation'],
  ['] 必须是对象', '#4340 DEFER：reportBuilder validation fragment'],
  ['].id 必须是非空字符串', '#4340 DEFER：reportBuilder validation fragment'],
  ['].valueConfig 必须是对象', '#4340 DEFER：reportBuilder validation fragment'],
  ['].valueConfig.chartType 当前不受支持', '#4340 DEFER：reportBuilder validation fragment'],
  ['schema_version 仅支持 1，收到', '#4340 DEFER：reportBuilder validation fragment'],
  ['统一取数响应格式无效', '#4340 DEFER：sourceDataResponse contract'],
  ['同一请求不能声明多个组织控件参数', '#4340 DEFER：widgetDataTransform org param'],
  ['无数据', '#4340 DEFER：topology registerNode empty caption'],
  ['副本', '#4340 DEFER：widgetCopy name suffix'],

  // stringParamMultiple 迁移提示（开发期警告，非产品文案）
  [
    '旧 stringList 与 componentSwitch 互斥；已保留列表传参（multiple: true）并关闭 componentSwitch',
    '#4340 DEFER：stringParamMultipleMigrate console/migrate note',
  ],
  [
    '同时存在 string 与 stringList，配置不兼容；已以 stringList 侧为准合并为',
    '#4340 DEFER：stringParamMultipleMigrate fragment',
  ],
  ['筛选项', '#4340 DEFER：stringParamMultipleMigrate fragment'],

  // shareMode 守卫开发期错误前缀
  ['NetworkTopology shareMode 禁止调用编辑接口:', '#4340 DEFER：shareMode guard / console-adjacent'],
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
