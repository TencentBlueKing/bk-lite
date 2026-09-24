import './test-mocks';

import { App } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { ReportContractGuideDrawer } from '../components/report-contract-guide-drawer';

describe('报告契约与模板语法抽屉', () => {
  afterEach(cleanup);
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('可从链接打开，并切换输出结构与模板语法', () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App>
      <ReportContractGuideDrawer defaultTab="template" triggerLabel="模板语法说明" />
    </App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: '模板语法说明' }));
    expect(screen.getByRole('dialog', { name: '模板与数据说明' })).not.toBeNull();
    expect(screen.getByText('怎么工作')).not.toBeNull();
    expect(screen.getByText('Word（docxtpl）')).not.toBeNull();
    expect(screen.getByText('Excel（xlsxjinja）')).not.toBeNull();
    expect(screen.getByText('Word 版式')).not.toBeNull();
    expect(screen.getByText('明确支持')).not.toBeNull();
    expect(screen.getAllByText(/\{\{\s*summary\.total\s*\}\}/).length).toBeGreaterThan(0);
    expect(screen.getByText(/非循环区域的静态合并单元格/)).not.toBeNull();
    expect(screen.getByText(/不支持循环内按数据动态合并单元格/)).not.toBeNull();
    expect(screen.getByText(/不支持旧的 Carbone/)).not.toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: '输出结构' }));
    expect(screen.getByText('平台固定外层')).not.toBeNull();
    expect(screen.getByText('数据如何进模板')).not.toBeNull();
    expect(screen.getAllByText(/BK_LITE_RESULT=/).length).toBeGreaterThan(0);
    expect(screen.getByText(/results\[\]\.data/)).not.toBeNull();
  });

  it('按入口打开对应 tab', () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App>
      <ReportContractGuideDrawer defaultTab="structure" triggerLabel="数据结构说明" />
    </App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: '数据结构说明' }));
    expect(screen.getByText('平台固定外层')).not.toBeNull();
    expect(screen.getByText('数据如何进模板')).not.toBeNull();
    expect(screen.queryByText('怎么工作')).toBeNull();
  });
});
