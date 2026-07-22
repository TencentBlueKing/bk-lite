import fs from 'node:fs';
import path from 'node:path';

const rendererPath = path.join(
  process.cwd(),
  'src/app/monitor/hooks/integration/useConfigRenderer.tsx'
);
const source = fs.readFileSync(rendererPath, 'utf8');

const expectations = [
  [
    /guide_short\s*,\s*tooltip/,
    'UI.json 的 tooltip 字段应被配置表单读取'
  ],
  [
    /const guideTip = guide_short \|\| tooltip;/,
    'tooltip 应作为 guide_short 的兼容兜底'
  ],
  [
    /<FieldGuideTip short=\{guideTip\} \/>/,
    '字段标签应将 tooltip 内容传给悬浮指引组件'
  ]
];

const failures = expectations
  .filter(([pattern]) => !pattern.test(source))
  .map(([, message]) => message);

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'));
  process.exit(1);
}

console.log('monitor config renderer tooltip support OK');
