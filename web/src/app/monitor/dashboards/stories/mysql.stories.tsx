import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/mysql';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * MySQL 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/MySQL',
  component: Dashboard,
  parameters: dashboardPreviewParameters('mysql')
};

export default meta;

/** 现状风格（Clean Light SaaS）— 对比基准 */
export const Default: StoryObj<typeof Dashboard> = {};
