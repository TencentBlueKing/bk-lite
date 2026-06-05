import type { Meta, StoryObj } from '@storybook/react';
import Dashboard from '../objects/elasticsearch';
import { dashboardPreviewParameters } from './story-helpers';

/**
 * Elasticsearch 监控仪表盘 — 无后端视觉预览（合成数据）。
 */
const meta: Meta<typeof Dashboard> = {
  title: 'Monitor/Dashboards/Elasticsearch',
  component: Dashboard,
  parameters: dashboardPreviewParameters('elasticsearch')
};

export default meta;

export const Default: StoryObj<typeof Dashboard> = {};
