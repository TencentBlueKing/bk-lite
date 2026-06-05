import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/activemq';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * ActiveMQ 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/ActiveMQ',
  component: Dashboard,
  parameters: dashboardPreviewParameters('activemq')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
