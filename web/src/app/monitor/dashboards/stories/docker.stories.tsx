import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/docker';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Docker 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Docker',
  component: Dashboard,
  parameters: dashboardPreviewParameters('docker')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
