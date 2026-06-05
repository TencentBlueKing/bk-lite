import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/zookeeper';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Zookeeper 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Zookeeper',
  component: Dashboard,
  parameters: dashboardPreviewParameters('zookeeper')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
