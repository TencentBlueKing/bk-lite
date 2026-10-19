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

  it('模板语法入口只展示语法内容，不出现输出结构与 Tab', () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App>
      <ReportContractGuideDrawer mode="template" triggerLabel="模板语法说明" />
    </App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: '模板语法说明' }));
    expect(screen.getByRole('dialog', { name: '模板语法说明' })).not.toBeNull();
    expect(screen.getByText('怎么工作')).not.toBeNull();
    expect(screen.getByText('Word（docxtpl）')).not.toBeNull();
    expect(screen.getByText('Excel（xlsxjinja）')).not.toBeNull();
    expect(screen.getAllByText(/\{\{\s*summary\.total\s*\}\}/).length).toBeGreaterThan(0);
    expect(screen.queryByRole('tab', { name: '输出结构' })).toBeNull();
    expect(screen.queryByText('平台固定外层')).toBeNull();
  });

  it('文档数据结构入口只展示结构内容，并保留模板衔接说明', () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App>
      <ReportContractGuideDrawer mode="structure" audience="document" triggerLabel="数据结构说明" />
    </App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: '数据结构说明' }));
    expect(screen.getByRole('dialog', { name: '数据结构说明' })).not.toBeNull();
    expect(screen.getByText('平台固定外层')).not.toBeNull();
    expect(screen.getByText('数据如何进模板')).not.toBeNull();
    expect(screen.getAllByText(/BK_LITE_RESULT=/).length).toBeGreaterThan(0);
    expect(screen.queryByRole('tab', { name: '模板语法' })).toBeNull();
    expect(screen.queryByText('怎么工作')).toBeNull();
  });

  it('作业脚本输出说明只展示输出结构，不含模板语法', () => {
    render(<IntlProvider locale="zh-CN" messages={{}}><App>
      <ReportContractGuideDrawer mode="structure" audience="job" triggerLabel="脚本输出说明" />
    </App></IntlProvider>);

    fireEvent.click(screen.getByRole('button', { name: '脚本输出说明' }));
    expect(screen.getByRole('dialog', { name: '脚本输出说明' })).not.toBeNull();
    expect(screen.getByText('平台固定外层')).not.toBeNull();
    expect(screen.getByText('每台主机的脚本要输出什么')).not.toBeNull();
    expect(screen.getByText(/这个名字不能改/)).not.toBeNull();
    expect(screen.getByText(/平台只认这个前缀/)).not.toBeNull();
    expect(screen.getByText(/根必须是 JSON 对象/)).not.toBeNull();
    expect(screen.getByText('下游拿到的完整结果')).not.toBeNull();
    expect(screen.getByText(/下面这份 JSON 由平台组装/)).not.toBeNull();
    expect(screen.queryByText('数据如何进模板')).toBeNull();
    expect(screen.queryByText('怎么工作')).toBeNull();
    expect(screen.queryByRole('tab')).toBeNull();
  });
});
