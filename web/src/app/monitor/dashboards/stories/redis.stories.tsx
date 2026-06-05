import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/redis';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Redis 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Redis',
  component: Dashboard,
  parameters: dashboardPreviewParameters('redis')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
