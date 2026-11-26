import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { defaultBasicSettings, ItsmRuntimeSettingsProvider, useItsmRuntimeSettings } from './runtime-settings';

const get = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ usePathname: () => '/itsm/portal' }));
vi.mock('@/utils/request', () => ({ default: () => ({ get, isLoading: false }) }));

function RuntimeConsumer() {
  const { settings, updateSettings } = useItsmRuntimeSettings();
  return <><p>{settings.product_name}</p>
    <button onClick={() => updateSettings({ ...settings, product_name: '运维服务台', tab_title: '运维工作台' })}>应用已保存的设置</button>
  </>;
}

describe('ITSM 基础设置运行时', () => {
  it('使用当前组织的配置并在离开应用后恢复原标题', async () => {
    document.title = 'BlueKing Lite';
    get.mockResolvedValue({ ...defaultBasicSettings, product_name: '研发服务台', tab_title: '研发工作台' });
    const view = render(<ItsmRuntimeSettingsProvider><RuntimeConsumer /></ItsmRuntimeSettingsProvider>);
    expect(await screen.findByText('研发服务台')).toBeTruthy();
    expect(document.title).toBe('研发工作台');
    fireEvent.click(screen.getByRole('button', { name: '应用已保存的设置' }));
    await waitFor(() => expect(document.title).toBe('运维工作台'));
    expect(screen.getByText('运维服务台')).toBeTruthy();
    view.unmount();
    expect(document.title).toBe('BlueKing Lite');
  });
});
