import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/rabbitmq';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * RabbitMQ 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/RabbitMQ',
  component: Dashboard,
  parameters: dashboardPreviewParameters('rabbitmq')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
