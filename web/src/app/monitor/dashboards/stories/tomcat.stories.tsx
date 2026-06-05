import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/tomcat';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Tomcat 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Tomcat',
  component: Dashboard,
  parameters: dashboardPreviewParameters('tomcat')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
