import assert from 'node:assert/strict';
import test from 'node:test';

import { PAGE_CONTEXT_TEXT_BUDGET } from '@/components/ai-page-context/types';
import { buildDashboardEditStateSection, dashboardEditStateAllowsApply } from '../dashboardEditContext';

test('edit state section serializes the complete structured dashboard snapshot', () => {
  const section = buildDashboardEditStateSection({
    dashboardId: 7,
    name: '资产概览',
    layout: [{
      i: 'card-1',
      x: 0,
      y: 0,
      w: 3,
      h: 2,
      name: '资产总数',
      valueConfig: {
        chartType: 'single',
        dataSource: 23,
        selectedFields: ['value'],
        eventTimeline: { timeField: 'occurred_at' },
        nodeGraphIdentityMode: 'field',
        thresholdColors: [{ value: '10', color: 'sentinel-crimson' }],
      },
    }],
    filters: [{
      id: 'organization__string',
      key: 'organization',
      name: '组织',
      type: 'string',
      defaultValue: 'org-default',
      order: 0,
      enabled: true,
      inputConfig: { control: 'organization' },
    }],
    filterValues: { organization__string: 'org-current' },
    otherConfig: { displayMode: 'compact' },
    refreshInterval: 60,
  });

  assert.equal(section.id, 'dashboard-edit-state');
  const snapshot = JSON.parse(section.content);
  assert.equal(snapshot.snapshotVersion, '1.0');
  assert.equal(snapshot.mode, 'edit');
  assert.equal(snapshot.layout[0].i, 'card-1');
  assert.deepEqual(snapshot.layout[0].valueConfig.thresholdColors, [{ value: '10', color: 'sentinel-crimson' }]);
  assert.deepEqual(snapshot.layout[0].valueConfig.selectedFields, ['value']);
  assert.equal(snapshot.layout[0].valueConfig.eventTimeline.timeField, 'occurred_at');
  assert.equal(snapshot.layout[0].valueConfig.nodeGraphIdentityMode, 'field');
  assert.equal(snapshot.filters[0].id, 'organization__string');
  assert.equal(snapshot.filterValues.organization__string, 'org-current');
  assert.equal(snapshot.otherConfig.displayMode, 'compact');
  assert.equal(snapshot.refreshInterval, 60);
});

test('edit state section is replaced when it cannot fit in one piece', () => {
  const section = buildDashboardEditStateSection({
    dashboardId: 7,
    name: 'x'.repeat(PAGE_CONTEXT_TEXT_BUDGET),
    layout: [],
    filters: [],
  });

  assert.equal(section.content.includes('无法安全搭盘'), true);
  assert.ok(section.content.length < PAGE_CONTEXT_TEXT_BUDGET);
  assert.equal(dashboardEditStateAllowsApply({
    dashboardId: 7,
    name: 'x'.repeat(PAGE_CONTEXT_TEXT_BUDGET),
    layout: [],
    filters: [],
  }), false);
});

test('dynamic filter source ref remains structured json', () => {
  const section = buildDashboardEditStateSection({
    dashboardId: 7,
    name: '资产概览',
    layout: [],
    filters: [{
      id: 'region__string',
      key: 'region',
      name: '区域',
      type: 'string',
      defaultValue: '',
      order: 0,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'region-list' },
          valueField: 'id',
          labelField: 'name',
        },
      },
    }],
  });

  const snapshot = JSON.parse(section.content);
  assert.deepEqual(snapshot.filters[0].inputConfig.optionsSource.sourceRef, {
    type: 'rest_api',
    value: 'region-list',
  });
});

test('long widget descriptions are omitted so visible values can share the page context budget', () => {
  const section = buildDashboardEditStateSection({
    dashboardId: 7,
    name: '告警',
    layout: [{
      i: 'ai-224-active_count',
      x: 0,
      y: 0,
      w: 4,
      h: 3,
      name: '未分派、待响应和处理中的告警数',
      description: '说明'.repeat(4000),
      valueConfig: { chartType: 'single', dataSource: 224 },
    }],
    filters: [],
  });

  const snapshot = JSON.parse(section.content);
  assert.equal(snapshot.layout[0].i, 'ai-224-active_count');
  assert.equal(snapshot.layout[0].description, undefined);
  assert.equal(dashboardEditStateAllowsApply({
    dashboardId: 7,
    name: '告警',
    layout: [{
      i: 'ai-224-active_count',
      x: 0,
      y: 0,
      w: 4,
      h: 3,
      name: '未分派、待响应和处理中的告警数',
      description: '说明'.repeat(4000),
      valueConfig: { chartType: 'single', dataSource: 224 },
    }],
    filters: [],
  }), true);
});

test('a short edit state still allows apply', () => {
  assert.equal(dashboardEditStateAllowsApply({
    dashboardId: 7,
    name: '资产概览',
    layout: [],
    filters: [],
  }), true);
});
