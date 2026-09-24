import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  HealthStatusTag,
  formatPowerState,
  getHealthTagProps,
  normalizeHealthStatus,
} from '../health';
import { getAssetColumns, getFieldItem } from '../common';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

describe('health and powerState utils', () => {
  it('normalizes health status values correctly', () => {
    expect(normalizeHealthStatus('OK')).toBe('OK');
    expect(normalizeHealthStatus('Healthy')).toBe('OK');
    expect(normalizeHealthStatus('Warning')).toBe('Warning');
    expect(normalizeHealthStatus('warn')).toBe('Warning');
    expect(normalizeHealthStatus('Critical')).toBe('Critical');
    expect(normalizeHealthStatus('error')).toBe('Critical');
    expect(normalizeHealthStatus('Unknown')).toBe('Unknown');
    expect(normalizeHealthStatus('Absent')).toBe('Unknown');
    expect(normalizeHealthStatus(null)).toBeNull();
    expect(normalizeHealthStatus('')).toBeNull();
  });

  it('gets correct tag props for health statuses', () => {
    expect(getHealthTagProps('OK')).toEqual({ color: 'success', text: 'OK' });
    expect(getHealthTagProps('Warning')).toEqual({ color: 'warning', text: 'Warning' });
    expect(getHealthTagProps('Critical')).toEqual({ color: 'error', text: 'Critical' });
    expect(getHealthTagProps('Unknown')).toEqual({ color: 'default', text: 'Unknown' });
  });

  it('renders HealthStatusTag with proper tag styling', () => {
    const { rerender } = render(<HealthStatusTag value="OK" />);
    expect(screen.getByText('OK')).toBeTruthy();

    rerender(<HealthStatusTag value="Warning" />);
    expect(screen.getByText('Warning')).toBeTruthy();

    rerender(<HealthStatusTag value="Critical" />);
    expect(screen.getByText('Critical')).toBeTruthy();

    rerender(<HealthStatusTag value="" />);
    expect(screen.getByText('--')).toBeTruthy();
  });

  it('formats power_state correctly', () => {
    expect(formatPowerState('On')).toBe('On');
    expect(formatPowerState('1')).toBe('On');
    expect(formatPowerState('Off')).toBe('Off');
    expect(formatPowerState('0')).toBe('Off');
    expect(formatPowerState(null)).toBe('--');
    expect(formatPowerState('')).toBe('--');
  });

  it('renders health and power_state in getAssetColumns and getFieldItem', () => {
    const attrList: AttrFieldType[] = [
      {
        attr_id: 'health',
        attr_name: '健康状态',
        attr_type: 'str',
        is_required: false,
        editable: false,
        option: [] as any,
      },
      {
        attr_id: 'power_state',
        attr_name: '电源状态',
        attr_type: 'str',
        is_required: false,
        editable: false,
        option: [] as any,
      },
      {
        attr_id: 'disk_life_percent',
        attr_name: '寿命百分比',
        attr_type: 'str',
        is_required: false,
        editable: false,
        option: [] as any,
      },
      {
        attr_id: 'nic_speed_mbps',
        attr_name: '速率(Mbps)',
        attr_type: 'str',
        is_required: false,
        editable: false,
        option: [] as any,
      },
    ];

    const cols = getAssetColumns({ attrList });
    expect(cols).toHaveLength(4);

    // Test health column render
    const healthCol = cols.find((c) => c.dataIndex === 'health');
    expect(healthCol).toBeDefined();

    // Test getFieldItem for health
    const healthFieldItem = getFieldItem({
      fieldItem: attrList[0],
      isEdit: false,
      value: 'OK',
    });
    expect(healthFieldItem).toBeDefined();

    // Test getFieldItem for power_state
    const powerFieldItem = getFieldItem({
      fieldItem: attrList[1],
      isEdit: false,
      value: 'On',
    });
    expect(powerFieldItem).toBe('On');

    // Test getFieldItem for copy mode (hideUserAvatar: true)
    const healthCopy = getFieldItem({
      fieldItem: attrList[0],
      isEdit: false,
      value: 'OK',
      hideUserAvatar: true,
    });
    expect(healthCopy).toBe('OK');
  });
});
