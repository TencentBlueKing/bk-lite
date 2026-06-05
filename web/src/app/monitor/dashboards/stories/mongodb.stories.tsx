import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/mongodb';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * MongoDB 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/MongoDB',
  component: Dashboard,
  parameters: dashboardPreviewParameters('mongodb')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
