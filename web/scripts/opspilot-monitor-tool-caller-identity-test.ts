import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildSkillSaveTools,
  buildStudioRuntimeTools,
  isMonitorToolConfig,
  normalizeMonitorToolConfig,
  normalizeMonitorToolConfigs,
} from '../src/app/opspilot/utils/monitorToolConfig';

const historicalKwargs = [
  { key: 'username', value: 'alice', type: 'text' },
  { key: 'password', value: 'legacy-secret', type: 'password' },
  { key: 'domain', value: 'example' },
  { key: 'team_id', value: 42 },
];

const legacyMonitor = {
  id: -6,
  name: '监控',
  rawName: 'monitor',
  icon: 'gongjuji',
  kwargs: historicalKwargs,
};
const normalizedMonitor = normalizeMonitorToolConfig(legacyMonitor);

assert.equal(isMonitorToolConfig(legacyMonitor), true);
assert.deepEqual(
  normalizedMonitor,
  {
    ...legacyMonitor,
    kwargs: [],
  },
  'loading a persisted Monitor tool must remove all historical credentials and team fields',
);
assert.notEqual(normalizedMonitor, legacyMonitor, 'normalizing Monitor must not mutate the source object');
assert.equal(legacyMonitor.kwargs, historicalKwargs, 'normalizing Monitor must leave source kwargs untouched');

const persistedMonitorWithoutRawName = {
  id: -6,
  name: 'monitor',
  icon: 'gongjuji',
  kwargs: historicalKwargs,
};
assert.equal(isMonitorToolConfig(persistedMonitorWithoutRawName), true);
assert.deepEqual(
  normalizeMonitorToolConfig(persistedMonitorWithoutRawName).kwargs,
  [],
  'the persisted canonical name must identify Monitor when rawName is unavailable',
);

assert.equal(
  isMonitorToolConfig({ name: 'monitor', rawName: 'legacy-alias' }),
  false,
  'an explicit non-Monitor rawName must take precedence over the display or persisted name',
);
assert.equal(
  isMonitorToolConfig({ name: 'Monitor' }),
  false,
  'Monitor detection must use the lowercase server canonical name instead of display labels',
);

const regularTool = {
  id: 7,
  name: 'MySQL',
  rawName: 'mysql',
  icon: 'gongjuji',
  kwargs: [
    { key: 'host', value: 'db.example.com' },
    { key: '', value: 'must-not-be-saved' },
  ],
};
assert.equal(
  normalizeMonitorToolConfig(regularTool),
  regularTool,
  'normalization must preserve a non-Monitor tool and its object identity',
);

const normalizedForBoundary = normalizeMonitorToolConfigs([legacyMonitor, regularTool]);
assert.deepEqual(
  normalizedForBoundary[0].kwargs,
  [],
  'save and Studio run boundaries must receive credential-free Monitor kwargs',
);
assert.equal(
  normalizedForBoundary[1],
  regularTool,
  'save and Studio run boundaries must preserve non-Monitor tools exactly',
);

assert.deepEqual(
  buildSkillSaveTools([legacyMonitor, regularTool]),
  [
    {
      id: -6,
      name: 'monitor',
      icon: 'gongjuji',
      kwargs: [],
    },
    {
      id: 7,
      name: 'mysql',
      icon: 'gongjuji',
      kwargs: [{ key: 'host', value: 'db.example.com' }],
    },
  ],
  'the Skill save boundary must canonicalize names, filter empty keys, and scrub Monitor kwargs',
);

const studioRuntimeTools = buildStudioRuntimeTools([legacyMonitor, regularTool]);
assert.deepEqual(
  studioRuntimeTools[0].kwargs,
  [],
  'the Studio runtime boundary must scrub Monitor kwargs',
);
assert.equal(
  studioRuntimeTools[1],
  regularTool,
  'the Studio runtime boundary must preserve non-Monitor tools exactly',
);

const monitorToolConfigSource = readFileSync(
  new URL('../src/app/opspilot/utils/monitorToolConfig.ts', import.meta.url),
  'utf8',
);
assert.match(
  monitorToolConfigSource,
  /import type \{ SelectTool, ToolVariable \}/,
  'normalization and boundary helpers must use the real SelectTool contract',
);
assert.doesNotMatch(
  monitorToolConfigSource,
  /<T extends MonitorToolConfigLike>/,
  'the normalizer must not claim an unsound generic return type',
);

const toolSelectorSource = readFileSync(
  new URL('../src/app/opspilot/components/skill/toolSelector.tsx', import.meta.url),
  'utf8',
);
assert.match(
  toolSelectorSource,
  /const normalizedDefaultTools = normalizeMonitorToolConfigs\(defaultTools\)/,
  'tool selection load/merge must scrub persisted Monitor kwargs',
);
assert.match(
  toolSelectorSource,
  /const commitSelectedTools = \(nextTools: SelectTool\[\]\) => \{\s*const normalizedTools = normalizeMonitorToolConfigs\(nextTools\);\s*setSelectedTools\(normalizedTools\);\s*onChange\(normalizedTools\);\s*\}/,
  'the ToolSelector commit boundary must normalize state and output together',
);
assert.equal(
  toolSelectorSource.match(/\bsetSelectedTools\(/g)?.length,
  1,
  'ToolSelector must have exactly one selected-tool state write',
);
assert.equal(
  toolSelectorSource.match(/\bonChange\(/g)?.length,
  1,
  'ToolSelector must have exactly one selected-tool output call',
);
assert.match(
  toolSelectorSource,
  /isMonitorToolConfig\(editingTool\) \? \(\s*<Alert/,
  'Monitor edit UI must show the caller identity notice instead of credential fields',
);
assert.doesNotMatch(
  toolSelectorSource,
  /GroupTreeSelect/,
  'Monitor must not expose the historical team selector',
);

const skillSettingsSource = readFileSync(
  new URL('../src/app/opspilot/(pages)/skill/detail/settings/page.tsx', import.meta.url),
  'utf8',
);
assert.match(
  skillSettingsSource,
  /setSelectedTools\(normalizeMonitorToolConfigs\(data\.tools as SelectTool\[\]\)\)/,
  'loading Skill details must scrub persisted Monitor kwargs before they enter state',
);
assert.match(
  skillSettingsSource,
  /tools: buildSkillSaveTools\(selectedTools\),/,
  'the final save payload must use the typed Monitor-safe boundary helper',
);
assert.match(
  skillSettingsSource,
  /tools: buildStudioRuntimeTools\(selectedTools\),/,
  'the Studio direct-run payload must use the typed Monitor-safe boundary helper',
);

console.log('opspilot Monitor caller identity tool config: pass');
