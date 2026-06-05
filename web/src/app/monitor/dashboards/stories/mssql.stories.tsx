import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/mssql';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * MSSQL 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/MSSQL',
  component: Dashboard,
  parameters: dashboardPreviewParameters('mssql')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
