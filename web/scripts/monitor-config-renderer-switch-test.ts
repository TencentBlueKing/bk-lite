import fs from 'fs';
import path from 'path';

const rendererPath = path.join(
  process.cwd(),
  'src/app/monitor/hooks/integration/useConfigRenderer.tsx'
);
const source = fs.readFileSync(rendererPath, 'utf8');

const expectations: Array<[RegExp, string]> = [
  [/case 'switch':/, 'renderTableColumn should support switch columns'],
  [/<Switch\s+/, 'switch columns should render an Ant Design Switch'],
  [
    /checked=\{Boolean\(text\)\}/,
    'switch columns should coerce row values to checked state'
  ],
  [
    /onChange=\{\(checked\) => handleChange\(checked, record, index\)\}/,
    'switch columns should write boolean changes back to the table row'
  ],
  [
    /const \{ width: columnWidth, \.\.\.componentProps \} = widget_props;/,
    'column width should be separated from component props'
  ],
  [/width: columnWidth \|\| 200/, 'column width should still drive table layout']
];

const failures = expectations
  .filter(([pattern]) => !pattern.test(source))
  .map(([, message]) => message);

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'));
  process.exit(1);
}

console.log('monitor config renderer switch support OK');
