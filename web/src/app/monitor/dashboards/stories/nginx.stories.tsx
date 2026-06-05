import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/nginx';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Nginx 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Nginx',
  component: Dashboard,
  parameters: dashboardPreviewParameters('nginx')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
