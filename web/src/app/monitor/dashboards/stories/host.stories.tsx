import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/host';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Host 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Host',
  component: Dashboard,
  parameters: dashboardPreviewParameters('host')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
