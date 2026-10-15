import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { WidgetConfigBasicFields } from '../widgetConfigBasicFields';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

const renderFields = (surface?: 'dashboard' | 'report' | 'screen') =>
  render(
    <Form>
      <WidgetConfigBasicFields
        t={(key) => key}
        chartType="table"
        showChartThemeMode={false}
        isNetworkStatusTopology={false}
        surface={surface}
      />
    </Form>,
  );

describe('WidgetConfigBasicFields', () => {
  it('keeps the description field on dashboard and report', () => {
    const { unmount } = renderFields('dashboard');
    expect(screen.getByLabelText('dataSource.describe')).toBeTruthy();
    unmount();

    renderFields('report');
    expect(screen.getByLabelText('dataSource.describe')).toBeTruthy();
  });

  it('omits the description field on the screen surface', () => {
    renderFields('screen');

    expect(screen.getByLabelText('dashboard.widgetName')).toBeTruthy();
    expect(screen.queryByLabelText('dataSource.describe')).toBeNull();
  });
});
