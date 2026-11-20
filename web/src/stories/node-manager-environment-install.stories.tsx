import React, { useEffect, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { IntlProvider } from 'react-intl';
import EnvironmentInstall from '@/app/node-manager/components/environment-install';
import { useThemeMode } from '@/theme';
import common from '@/locales/zh.json';
import node from '@/app/node-manager/locales/zh.json';
import { configureEnvironmentPreview, type EnvironmentPreviewState } from '../../.storybook/mocks/node-environment-request';

const flatten = (object: Record<string, unknown>, prefix = '', result: Record<string, string> = {}) => {
  Object.entries(object).forEach(([key, value]) => {
    const name = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') flatten(value as Record<string, unknown>, name, result);
    else result[name] = String(value);
  });
  return result;
};
const messages = { ...flatten(common), ...flatten(node) };

const Preview = ({ dark = false, state = 'ready' }: { dark?: boolean; state?: EnvironmentPreviewState }) => {
  const { setMode } = useThemeMode();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    configureEnvironmentPreview(state);
    setMode(dark ? 'dark' : 'light');
    setReady(true);
  }, [dark, state, setMode]);
  if (!ready) return null;
  return <IntlProvider locale="zh" messages={messages}>
    <EnvironmentInstall key={`${state}-${dark}`} open cloudId={1} onClose={() => undefined} />
  </IntlProvider>;
};

const meta = { title: 'Node Manager/Environment Installer', component: Preview, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof Preview>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Dark: Story = { args: { dark: true } };
export const Empty: Story = { args: { state: 'empty' } };
export const Unavailable: Story = { args: { state: 'error' } };
export const LongVersion: Story = { args: { state: 'long' } };
