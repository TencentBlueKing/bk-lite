import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/apache';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Apache 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Apache',
  component: Dashboard,
  parameters: dashboardPreviewParameters('apache')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
