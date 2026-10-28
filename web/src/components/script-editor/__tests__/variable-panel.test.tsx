import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ScriptEditor, { type ScriptVariable } from '@/components/script-editor';

const messages = {
  'common.optionalVariables': '可选变量',
  'common.collapse': '收起',
  'common.variableName': '变量名',
  'common.description': '描述',
  'common.actions': '操作',
  'common.useVariable': '选用',
  'common.copy': '复制',
  'common.fullscreen': '全屏',
  'common.copySuccess': '已复制',
  'common.exitFullscreen': '退出全屏',
};

const variables: ScriptVariable[] = [
  {
    key: 'BK_JOB_USER',
    description: '执行用户',
    token: {
      shell: '$BK_JOB_USER',
      powershell: '$BK_JOB_USER',
      python: 'BK_JOB_USER',
      bat: '%BK_JOB_USER%',
    },
  },
];

const renderEditor = (props: ComponentProps<typeof ScriptEditor>) => render(
  <IntlProvider locale="zh" messages={messages} onError={() => undefined}>
    <ScriptEditor {...props} />
  </IntlProvider>,
);

describe('ScriptEditor variable panel', () => {
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

  afterEach(cleanup);

  it('hides the variable rail unless the caller turns it on', () => {
    renderEditor({ value: { shell: 'echo hi' }, activeLang: 'shell' });
    expect(screen.queryByRole('button', { name: '可选变量' })).toBeNull();
  });

  it('starts collapsed and inserts the token for the active language', () => {
    const onChange = vi.fn();
    renderEditor({
      value: { shell: 'echo hi', python: 'print(1)' },
      activeLang: 'shell',
      onChange,
      variablePanel: {
        visible: true,
        followFullscreen: false,
        defaultExpanded: false,
        variables,
      },
    });

    expect(screen.queryByRole('button', { name: '选用' })).toBeNull();
    const toggle = screen.getByRole('button', { name: '可选变量' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.textContent).toContain('{x}');
    fireEvent.click(toggle);
    expect(screen.getByText('$BK_JOB_USER')).toBeTruthy();
    expect(screen.getByText('执行用户')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '选用' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      shell: 'echo hi$BK_JOB_USER',
    }));
  });

  it('shows the python token after the language tab changes', () => {
    const onLangChange = vi.fn();
    const { rerender } = renderEditor({
      value: { shell: 'echo hi', python: 'print(1)' },
      activeLang: 'shell',
      onLangChange,
      variablePanel: { visible: true, defaultExpanded: true, variables },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Python' }));
    expect(onLangChange).toHaveBeenCalledWith('python');
    rerender(
      <IntlProvider locale="zh" messages={messages} onError={() => undefined}>
        <ScriptEditor
          value={{ shell: 'echo hi', python: 'print(1)' }}
          activeLang="python"
          onLangChange={onLangChange}
          variablePanel={{ visible: true, defaultExpanded: true, variables }}
        />
      </IntlProvider>,
    );
    expect(screen.getByText('BK_JOB_USER')).toBeTruthy();
    expect(screen.queryByText('$BK_JOB_USER')).toBeNull();
  });
});
