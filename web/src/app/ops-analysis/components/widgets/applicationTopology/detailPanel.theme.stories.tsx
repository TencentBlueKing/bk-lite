import React, { useEffect } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button } from 'antd';
import { IntlProvider } from 'react-intl';
import ScreenWidgetThemeProvider from '@/app/ops-analysis/components/screenWidgetThemeProvider';
import OperateDrawer from '@/components/operate-drawer';
import zhOps from '@/app/ops-analysis/locales/zh.json';
import { useThemeMode } from '@/theme';
import type { ApplicationTopologyBandNode } from './bandModel';
import ApplicationTopologyDetailPanel from './detailPanel';

type LocaleJson = Record<string, unknown>;

const flatten = (obj: LocaleJson, prefix = '', out: Record<string, string> = {}) => {
  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const next = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as LocaleJson, next, out);
    } else {
      out[next] = String(value);
    }
  });
  return out;
};

const messages = flatten(zhOps as LocaleJson);

const node: ApplicationTopologyBandNode = {
  id: '8a8583a6-8352-4394-912f-b2c8f982bc18',
  name: 'bj-pay-worker-01',
  modelId: 'host',
  layer: 'host',
  tone: 'normal',
  alertCount: 0,
  maxLevel: null,
  monitorId: '',
  badge: null,
  category: 'host',
  x: 0,
  y: 0,
};

const Shell = ({
  systemMode,
  presentedAlone,
}: {
  systemMode: 'light' | 'dark';
  presentedAlone: boolean;
}) => {
  const { mode, setMode } = useThemeMode();
  useEffect(() => {
    setMode(systemMode);
  }, [setMode, systemMode]);

  return (
    <IntlProvider locale="zh" messages={messages}>
      <div
        data-theme-ready={mode === systemMode ? 'true' : 'false'}
        style={{
          display: 'flex',
          minHeight: '100vh',
          background: presentedAlone ? '#0c2138' : 'var(--color-bg)',
          color: 'var(--color-text-1)',
        }}
      >
        {presentedAlone ? null : (
          <aside
            style={{
              width: 220,
              flex: 'none',
              borderRight: '1px solid var(--color-border-1)',
              background: 'var(--color-bg-1)',
              padding: 16,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 12 }}>目录管理</div>
            <div style={{ color: 'var(--color-text-2)' }}>应用拓扑大屏</div>
          </aside>
        )}
        <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
          <div
            style={{
              height: 48,
              display: 'flex',
              alignItems: 'center',
              padding: '0 16px',
              borderBottom: presentedAlone ? 'none' : '1px solid var(--color-border-1)',
              background: presentedAlone ? 'transparent' : 'var(--color-bg-1)',
            }}
          >
            {presentedAlone ? '大屏分享' : '运营分析'}
          </div>
          <ScreenWidgetThemeProvider mode="screen-dark">
            <div style={{ height: 'calc(100vh - 48px)' }} />
            <ApplicationTopologyDetailPanel
              node={node}
              statusLabel="正常"
              shareMode={presentedAlone}
              chartThemeMode="screen-dark"
              onClose={() => undefined}
            />
          </ScreenWidgetThemeProvider>
          <OperateDrawer
            title="系统抽屉"
            subTitle="OperateDrawer"
            open
            width={380}
            placement="left"
            mask={false}
            footer={<Button>关闭</Button>}
          >
            <div
              style={{
                border: '1px solid var(--color-border-1)',
                borderRadius: 8,
                background: 'var(--color-bg)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '8px 12px',
                  background: 'var(--color-fill-1)',
                  color: 'var(--color-text-1)',
                  fontWeight: 600,
                }}
              >
                基本信息
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '88px 1fr' }}>
                <div style={{ padding: 10, background: 'var(--color-fill-1)', color: 'var(--color-text-2)' }}>实例名</div>
                <div style={{ padding: 10, color: 'var(--color-text-1)' }}>settle-core-01</div>
              </div>
            </div>
          </OperateDrawer>
        </div>
      </div>
    </IntlProvider>
  );
};

const meta = {
  title: 'OpsAnalysis/Widgets/ApplicationTopologyDetail',
  component: Shell,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof Shell>;

export default meta;

type Story = StoryObj<typeof meta>;

export const EmbeddedSystemLight: Story = {
  render: () => <Shell systemMode="light" presentedAlone={false} />,
};

export const EmbeddedSystemDark: Story = {
  render: () => <Shell systemMode="dark" presentedAlone={false} />,
};

export const ShareScreenDark: Story = {
  render: () => <Shell systemMode="light" presentedAlone />,
};
