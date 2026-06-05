import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/ping';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Ping 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Ping',
  component: Dashboard,
  parameters: dashboardPreviewParameters('ping')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
