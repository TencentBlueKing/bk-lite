import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveTableCellPresentation } from '../tableCellStyle';

test('text mode uses mapping color before threshold color', () => {
  const presentation = resolveTableCellPresentation('关注', {
    cellType: 'text',
    valueMappings: [
      { type: 'value', value: '关注', result: { color: '#EAB839', text: '关注中' } },
    ],
    cellThresholdColors: [{ value: '0', color: '#fd666d' }],
  });

  assert.deepEqual(presentation, {
    mode: 'text',
    displayText: '关注中',
    color: '#EAB839',
  });
});

test('colorBackground uses pure color block with tooltip text', () => {
  const presentation = resolveTableCellPresentation('正常', {
    cellType: 'colorBackground',
    valueMappings: [
      { type: 'value', value: '正常', result: { color: '#67a567' } },
    ],
  });

  assert.deepEqual(presentation, {
    mode: 'colorBackground',
    color: '#67a567',
    tooltipText: '正常',
  });
});

test('colorBackground without color falls back to plain text', () => {
  const presentation = resolveTableCellPresentation('未知', {
    cellType: 'colorBackground',
    valueMappings: [],
  });

  assert.deepEqual(presentation, {
    mode: 'text',
    displayText: '未知',
  });
});

test('unconfigured column stays plain text without color', () => {
  const presentation = resolveTableCellPresentation('CAS01', {});
  assert.deepEqual(presentation, {
    mode: 'text',
    displayText: 'CAS01',
  });
});
