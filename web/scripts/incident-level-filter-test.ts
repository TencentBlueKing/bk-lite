import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const incidentPageSource = readFileSync(
  resolve(here, '../src/app/alarm/(pages)/incidents/page.tsx'),
  'utf8'
);

assert.doesNotMatch(
  incidentPageSource,
  /from ['"]@\/app\/alarm\/components\/alarmFilters['"]/,
  '事故页不得继续引用 camelCase alarmFilters（其内部写死 alert 等级）'
);
assert.match(
  incidentPageSource,
  /from ['"]@\/app\/alarm\/components\/alarm-filters['"]/,
  '事故页必须改用接受显式 levelOptions 的 alarm-filters'
);
assert.match(
  incidentPageSource,
  /toIncidentLevelFilterOptions\(\s*levelListIncident\s*\)/,
  '事故页必须把 incident 等级列表转成筛选项并传入'
);
assert.match(
  incidentPageSource,
  /levelOptions=\{toIncidentLevelFilterOptions\(levelListIncident\)\}/,
  '事故页必须把 incident 筛选项传给 AlarmFilters.levelOptions'
);
assert.match(
  incidentPageSource,
  /filterSource=\{false\}/,
  '事故页筛选仍不展示来源'
);
assert.match(
  incidentPageSource,
  /level:\s*filters\.level\.join\(['"],['"]\)/,
  '查询参数仍用 filters.level join 后的 level，不改 API'
);

async function main() {
  const { toIncidentLevelFilterOptions } = await import(
    '../src/app/alarm/utils/incidentLevelFilters.ts'
  );

  const incidentLevels = [
    {
      level_id: 1,
      level_display_name: '事故P1',
      color: '#ff4d4f',
    },
    {
      level_id: 7,
      level_display_name: '事故独有',
      color: '#722ed1',
    },
  ];

  const options = toIncidentLevelFilterOptions(incidentLevels);
  const byValue = new Map(options.map((item) => [item.value, item]));

  assert.equal(typeof options[0]?.value, 'string');
  assert.ok(
    byValue.has('7'),
    '仅属于 incident 的 level_id 必须出现在筛选项'
  );
  assert.equal(byValue.get('7')?.label, '事故独有');
  assert.equal(byValue.get('7')?.color, '#722ed1');

  assert.ok(
    !byValue.has('99'),
    '仅属于 alert 的等级不得进入事故筛选项'
  );

  const shared = byValue.get('1');
  assert.ok(shared, '同 ID 的事故等级必须出现在筛选项');
  assert.equal(
    shared?.label,
    '事故P1',
    '同 ID 不同名称时必须使用 incident 显示名'
  );
  assert.notEqual(shared?.label, '告警P1');
  assert.equal(shared?.value, String(1));

  console.log('incident level filter test passed');
}

main();
