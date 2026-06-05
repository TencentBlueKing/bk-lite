import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/postgresql';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * PostgreSQL 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/PostgreSQL',
  component: Dashboard,
  parameters: dashboardPreviewParameters('postgres')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
