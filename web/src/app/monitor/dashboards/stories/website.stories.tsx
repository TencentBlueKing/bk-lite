import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/website';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Website 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Website',
  component: Dashboard,
  parameters: dashboardPreviewParameters('website')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
