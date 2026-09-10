import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

type Messages = Record<string, unknown>;

const root = path.resolve(process.cwd());
const read = (relativePath: string) => fs.readFileSync(path.join(root, relativePath), 'utf8');
const flatten = (value: Messages, prefix = '', result: Record<string, string> = {}) => {
  for (const [key, item] of Object.entries(value)) {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (typeof item === 'string') result[nextKey] = item;
    else if (item && typeof item === 'object') flatten(item as Messages, nextKey, result);
  }
  return result;
};

const localePaths = ['src/app/apm/locales/zh.json', 'src/app/apm/locales/en.json'];
const [zh, en] = localePaths.map((localePath) => flatten(JSON.parse(read(localePath)) as Messages));
const commonEn = flatten(JSON.parse(read('src/locales/en.json')) as Messages);

for (const key of new Set([...Object.keys(zh), ...Object.keys(en)])) {
  if (!zh[key] || !en[key]) throw new Error(`APM locale key is not bilingual: ${key}`);
}

const dynamicKeys = [
  'apm.status.firing',
  'apm.status.recovered',
  'apm.severity.critical',
  'apm.severity.error',
  'apm.severity.warning',
  'apm.common.errorRate',
  'apm.common.p95Latency',
  'apm.common.p99Latency',
  'apm.common.throughput',
  'apm.alerts.notificationNone',
  'apm.alerts.notificationPending',
  'apm.alerts.notificationDelivered',
  'apm.alerts.notificationPartial',
  'apm.alerts.notificationFailed',
  'apm.alerts.deliveryPending',
  'apm.alerts.deliveryDelivered',
  'apm.alerts.deliveryFailed',
];
for (const key of dynamicKeys) {
  if (!zh[key] || !en[key]) throw new Error(`Missing dynamic APM locale key: ${key}`);
}

const collectSourcePaths = (directory: string): string[] => fs.readdirSync(path.join(root, directory), { withFileTypes: true })
  .flatMap((entry) => {
    const relativePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      return entry.name === '__tests__' ? [] : collectSourcePaths(relativePath);
    }
    return /\.(?:ts|tsx)$/.test(entry.name) && !/\.test\.(?:ts|tsx)$/.test(entry.name)
      ? [relativePath]
      : [];
  });

const sourcePaths = collectSourcePaths('src/app/apm');
const sourceErrors: string[] = [];

for (const sourcePath of sourcePaths) {
  const source = read(sourcePath);
  const sourceFile = ts.createSourceFile(sourcePath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't') {
      const first = node.arguments[0];
      if (first && ts.isStringLiteral(first)) {
        const key = first.text;
        if (!en[key] && !commonEn[key]) sourceErrors.push(`Missing APM English message used by ${sourcePath}: ${key}`);
      }
    }

    const isTemplatePart = node.kind === ts.SyntaxKind.TemplateHead
      || node.kind === ts.SyntaxKind.TemplateMiddle
      || node.kind === ts.SyntaxKind.TemplateTail;
    const text = ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node) || isTemplatePart
      ? (node as ts.LiteralLikeNode).text
      : '';
    if (text && !sourcePath.endsWith('/metric-format.ts')) {
      const isTranslationFallback = ts.isPropertyAssignment(node.parent)
        && ts.isIdentifier(node.parent.name)
        && ['fallback', 'defaultMessage'].includes(node.parent.name.text);
      let parent: ts.Node | undefined = node;
      let translated = isTranslationFallback;
      let machineSyntax = false;
      while (parent) {
        if (ts.isVariableDeclaration(parent)
          && ts.isIdentifier(parent.name)
          && /fallback/i.test(parent.name.text)) {
          translated = true;
          break;
        }
        if (ts.isVariableDeclaration(parent)
          && ts.isIdentifier(parent.name)
          && /(?:ICON|ASSET)/.test(parent.name.text)) {
          machineSyntax = true;
        }
        if (ts.isCallExpression(parent) && ts.isIdentifier(parent.expression) && parent.expression.text === 't') {
          translated = true;
          break;
        }
        if (ts.isCallExpression(parent)
          && ts.isPropertyAccessExpression(parent.expression)
          && ts.isIdentifier(parent.expression.expression)
          && parent.expression.expression.text === 'tokens'
          && parent.expression.name.text === 'push') {
          machineSyntax = true;
        }
        parent = parent.parent;
      }
      if (!translated && !machineSyntax && /[\u3400-\u9fff]/.test(text)) {
        const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
        sourceErrors.push(`Hardcoded APM UI copy remains at ${sourcePath}:${line}: ${text.trim()}`);
      }
      const fixedPresentation = /(?:Y{2,}|M{2}|D{2}|H{2}|s{2})[-/:]|(?:^|[\s(·])(?:req\/s|\/s|ms)(?=$|[\s)·])/;
      if (!translated && !machineSyntax && fixedPresentation.test(text)) {
        const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
        sourceErrors.push(`Non-localized APM date/unit format remains at ${sourcePath}:${line}: ${text.trim()}`);
      }
    }
    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
}

if (sourceErrors.length) {
  throw new Error([...new Set(sourceErrors)].join('\n'));
}
