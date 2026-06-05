import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/consul';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Consul 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Consul',
  component: Dashboard,
  parameters: dashboardPreviewParameters('consul')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
