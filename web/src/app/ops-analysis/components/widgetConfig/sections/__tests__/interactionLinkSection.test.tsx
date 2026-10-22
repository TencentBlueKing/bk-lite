import React, { createRef } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider, Form, type FormInstance } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import InteractionLinkSection from '@/app/ops-analysis/components/widgetConfig/sections/interactionLinkSection';

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

const translate = (key: string, fallback?: string) => fallback ?? key;

const KindValue = () => {
  const form = Form.useFormInstance();
  const kind = Form.useWatch(['interaction', 'kind'], form);
  return <div data-testid="kind">{kind}</div>;
};

const renderSection = (
  chartType: string,
  kind = 'title',
  titleLinkUnavailable = false,
) => {
  const formRef = createRef<FormInstance>();
  render(
    <ConfigProvider theme={{ token: { motion: false } }}>
      <Form
        ref={formRef}
        layout="vertical"
        initialValues={{
          interaction: { kind, name: '', url: '', openMode: 'sameTab' },
        }}
      >
        <InteractionLinkSection
          t={translate}
          chartType={chartType}
          definitions={[]}
          rawData={null}
          titleLinkUnavailable={titleLinkUnavailable}
        />
        <KindValue />
      </Form>
    </ConfigProvider>,
  );
  return formRef;
};

describe('InteractionLinkSection', () => {
  it('数据链接组件用分段选择器，说明只出现在问号提示里', async () => {
    const user = userEvent.setup();
    renderSection('line');

    expect(screen.queryByRole('heading', { name: '交互' })).toBeNull();
    expect(screen.getByText('链接类型')).toBeTruthy();
    expect(screen.queryByText('在标题旁显示图标。')).toBeNull();
    expect(screen.queryByText('输入 $ 选择要带上的值')).toBeNull();
    expect(screen.queryByText('输入 $ 引用全局筛选变量')).toBeNull();

    expect(screen.getByRole('radio', { name: '无' })).toBeTruthy();
    expect(screen.getByRole('radio', { name: '标题链接' })).toBeTruthy();
    expect(screen.getByRole('radio', { name: '数据链接' })).toBeTruthy();
    const groups = document.querySelectorAll('.ant-segmented');
    expect(groups).toHaveLength(2);
    expect(groups[0]?.className).not.toContain('ant-segmented-sm');
    expect(groups[1]?.className).toContain('ant-segmented-sm');

    const labels = [...document.querySelectorAll('.ant-form-item-label')].map((node) => node.textContent);
    expect(labels).toEqual(['名称', '目标 URL', '打开方式']);
    const urlLabel = screen.getByText('目标 URL').closest('label');
    expect(urlLabel?.className).toContain('ant-form-item-required');
    expect(screen.getByText('名称').closest('label')?.className).not.toContain('ant-form-item-required');
    expect(screen.getByPlaceholderText('输入 URL，键入 $ 插入变量')).toBeTruthy();

    await user.click(screen.getByText('数据链接'));
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('data');
    });

    await user.hover(screen.getByRole('img', { name: 'question-circle' }));
    expect(await screen.findByText('无：不设置跳转')).toBeTruthy();
    expect(screen.getByText('标题链接：标题行最右侧显示 > 图标')).toBeTruthy();
    expect(screen.getByText('数据链接：点击数据点、柱、扇区或数字打开')).toBeTruthy();
  });

  it('应用拓扑能选数据链接，并列出对象 id、名称和模型', async () => {
    const user = userEvent.setup();
    renderSection('applicationTopology', 'none');

    expect(screen.getByRole('radio', { name: '数据链接' })).toBeTruthy();
    await user.click(screen.getByText('数据链接'));
    const url = await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量');
    await user.type(url, '/cmdb?id=');
    await user.type(url, '$');

    expect(await screen.findByRole('option', { name: /对象 ID/ })).toBeTruthy();
    expect(screen.getByRole('option', { name: /对象名称/ })).toBeTruthy();
    expect(screen.getByRole('option', { name: /对象模型 ID/ })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /对象类型/ })).toBeNull();
    expect(screen.queryByRole('option', { name: /机柜 ID/ })).toBeNull();
  });

  it('只支持标题链接的组件用同一分段选择器，并把数据链接收成标题链接', async () => {
    const user = userEvent.setup();
    renderSection('text', 'data');

    expect(screen.getByText('链接类型')).toBeTruthy();
    expect(screen.getByRole('radio', { name: '无' })).toBeTruthy();
    expect(screen.getByRole('radio', { name: '标题链接' })).toBeTruthy();
    expect(screen.queryByRole('radio', { name: '数据链接' })).toBeNull();
    expect(document.querySelectorAll('.ant-segmented')).toHaveLength(2);
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('title');
    });

    await user.hover(screen.getByRole('img', { name: 'question-circle' }));
    expect(await screen.findByText('无：不设置跳转')).toBeTruthy();
    expect(screen.getByText('该组件仅支持标题链接，点击标题行最右侧 > 打开')).toBeTruthy();
  });

  it('选无时只留提示，切回后保留已填的 URL，并可以清空输入', async () => {
    const user = userEvent.setup();
    renderSection('line', 'none');

    expect(screen.getByText('未设置交互，组件不可点击跳转')).toBeTruthy();
    expect(screen.queryByText('名称')).toBeNull();
    expect(screen.queryByText('目标 URL')).toBeNull();
    expect(screen.queryByText('打开方式')).toBeNull();
    expect(document.querySelectorAll('.ant-segmented')).toHaveLength(1);
    expect(screen.getByTestId('kind').textContent).toBe('none');

    await user.click(screen.getByText('标题链接'));
    const url = await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量');
    await user.type(url, '/ops/detail');
    expect(document.querySelector('.ant-input-clear-icon')).toBeTruthy();

    await user.click(screen.getByText('无'));
    await waitFor(() => {
      expect(screen.getByText('未设置交互，组件不可点击跳转')).toBeTruthy();
    });
    expect(screen.queryByPlaceholderText('输入 URL，键入 $ 插入变量')).toBeNull();
    expect(screen.getByTestId('kind').textContent).toBe('none');

    await user.click(screen.getByText('标题链接'));
    const restored = await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量');
    expect((restored as HTMLInputElement).value).toBe('/ops/detail');

    await user.click(document.querySelector('.ant-input-clear-icon') as HTMLElement);
    await waitFor(() => {
      expect((screen.getByPlaceholderText('输入 URL，键入 $ 插入变量') as HTMLInputElement).value).toBe('');
    });
  });

  it('标题链接和数据链接必须填写 URL，选无时不拦截保存', async () => {
    const user = userEvent.setup();
    const formRef = renderSection('line', 'title');

    await act(async () => {
      await expect(formRef.current?.validateFields()).rejects.toBeTruthy();
    });
    expect(await screen.findByText('请输入 URL')).toBeTruthy();

    await user.click(screen.getByText('数据链接'));
    await user.type(screen.getByPlaceholderText('输入 URL，键入 $ 插入变量'), '   ');
    await act(async () => {
      await expect(formRef.current?.validateFields()).rejects.toBeTruthy();
    });

    await user.type(screen.getByPlaceholderText('输入 URL，键入 $ 插入变量'), '/ops');
    await act(async () => {
      await expect(formRef.current?.validateFields()).resolves.toMatchObject({
        interaction: { kind: 'data', url: '   /ops' },
      });
    });

    await user.click(screen.getByText('无'));
    await act(async () => {
      await expect(formRef.current?.validateFields()).resolves.toMatchObject({
        interaction: { kind: 'none' },
      });
    });
  });

  it('不允许的协议留在表单里，合法的 http 和站内路径可以保存', async () => {
    const user = userEvent.setup();
    const formRef = renderSection('line', 'title');
    const url = screen.getByPlaceholderText('输入 URL，键入 $ 插入变量');

    await user.type(url, 'javascript:alert(1)');
    await act(async () => {
      await expect(formRef.current?.validateFields()).rejects.toBeTruthy();
    });
    expect(await screen.findByText('链接协议不被允许')).toBeTruthy();

    await user.clear(url);
    await user.type(url, 'https://example.com/a');
    await act(async () => {
      await expect(formRef.current?.validateFields()).resolves.toMatchObject({
        interaction: { kind: 'title', url: 'https://example.com/a' },
      });
    });
  });

  it('无边框时标题链接置灰，已配置则保留并提示，仍可改成数据链接或无', async () => {
    const user = userEvent.setup();
    const formRef = renderSection('line', 'title', true);
    const titleRadio = screen.getByRole('radio', { name: '标题链接' }) as HTMLInputElement;

    expect(titleRadio.disabled).toBe(true);
    expect(titleRadio.closest('.ant-segmented-item')?.className).toContain('ant-segmented-item-selected');
    expect(formRef.current?.getFieldValue(['interaction', 'kind'])).toBe('title');
    expect(screen.getByText('当前为无边框样式，标题链接不会显示，切换为标准样式后生效')).toBeTruthy();

    await user.hover(screen.getByText('标题链接'));
    expect(await screen.findByText('无边框样式不显示标题，无法使用标题链接')).toBeTruthy();

    await user.click(screen.getByText('数据链接'));
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('data');
    });
    expect(screen.queryByText('当前为无边框样式，标题链接不会显示，切换为标准样式后生效')).toBeNull();
    expect(titleRadio.disabled).toBe(true);

    await user.click(screen.getByText('标题链接'));
    expect(screen.getByTestId('kind').textContent).toBe('data');

    await user.click(screen.getByText('无'));
    await waitFor(() => {
      expect(screen.getByText('未设置交互，组件不可点击跳转')).toBeTruthy();
    });
    expect(formRef.current?.getFieldValue(['interaction', 'kind'])).toBe('none');
  });

  it('无边框的标题链接组件只剩无可选，切回标准样式后标题链接恢复', async () => {
    const user = userEvent.setup();
    const formRef = createRef<FormInstance>();
    const tree = (titleLinkUnavailable: boolean) => (
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Form
          ref={formRef}
          layout="vertical"
          initialValues={{
            interaction: { kind: 'title', name: '查看详情', url: '/ops', openMode: 'sameTab' },
          }}
        >
          <InteractionLinkSection
            t={translate}
            chartType="text"
            definitions={[]}
            rawData={null}
            titleLinkUnavailable={titleLinkUnavailable}
          />
          <KindValue />
        </Form>
      </ConfigProvider>
    );
    const view = render(tree(true));

    expect(screen.queryByRole('radio', { name: '数据链接' })).toBeNull();
    const titleRadio = screen.getByRole('radio', { name: '标题链接' }) as HTMLInputElement;
    expect(titleRadio.disabled).toBe(true);
    expect(titleRadio.closest('.ant-segmented-item')?.className).toContain('ant-segmented-item-selected');
    expect(formRef.current?.getFieldValue(['interaction', 'kind'])).toBe('title');
    expect(screen.getByText('当前为无边框样式，标题链接不会显示，切换为标准样式后生效')).toBeTruthy();
    expect((screen.getByPlaceholderText('输入 URL，键入 $ 插入变量') as HTMLInputElement).value).toBe('/ops');

    await user.click(screen.getByText('无'));
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('none');
    });
    expect(screen.queryByText('当前为无边框样式，标题链接不会显示，切换为标准样式后生效')).toBeNull();

    await user.click(screen.getByText('标题链接'));
    expect(screen.getByTestId('kind').textContent).toBe('none');

    view.rerender(tree(false));
    const restored = screen.getByRole('radio', { name: '标题链接' }) as HTMLInputElement;
    expect(restored.disabled).toBe(false);
    await user.click(screen.getByText('标题链接'));
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('title');
    });
    expect(screen.queryByText('当前为无边框样式，标题链接不会显示，切换为标准样式后生效')).toBeNull();
    expect((screen.getByPlaceholderText('输入 URL，键入 $ 插入变量') as HTMLInputElement).value).toBe('/ops');
    expect(formRef.current?.getFieldValue(['interaction', 'url'])).toBe('/ops');
  });

  it('文本项只保留标题链接，选无会清空名称和 URL', async () => {
    const user = userEvent.setup();
    const formRef = createRef<FormInstance>();
    render(
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Form
          ref={formRef}
          layout="vertical"
          initialValues={{
            interaction: { kind: 'title', name: '详情', url: '/ops', openMode: 'newTab' },
          }}
        >
          <InteractionLinkSection
            t={translate}
            definitions={[]}
            rawData={null}
            besideText
            clearOnNone
          />
          <KindValue />
        </Form>
      </ConfigProvider>,
    );

    expect(screen.queryByRole('radio', { name: '数据链接' })).toBeNull();
    await user.hover(screen.getByRole('img', { name: 'question-circle' }));
    expect(await screen.findByText('标题链接：文本行最右侧显示 > 图标')).toBeTruthy();
    expect(screen.queryByText('该组件仅支持标题链接，点击标题行最右侧 > 打开')).toBeNull();

    await user.click(screen.getByText('无'));
    await waitFor(() => {
      expect(screen.getByTestId('kind').textContent).toBe('none');
    });
    expect(formRef.current?.getFieldValue(['interaction'])).toEqual({
      kind: 'none',
      name: '',
      url: '',
      openMode: 'sameTab',
    });

    await user.click(screen.getByText('标题链接'));
    expect((await screen.findByPlaceholderText('输入 URL，键入 $ 插入变量') as HTMLInputElement).value).toBe('');
    expect((screen.getByPlaceholderText('例如：查看详情') as HTMLInputElement).value).toBe('');
  });
});
