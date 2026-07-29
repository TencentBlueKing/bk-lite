import type { Meta, StoryObj } from '@storybook/nextjs';
import { IntegrationInstanceList } from './apm-integration-pages.components';

const meta = {
  title: 'APM/Integration Pages/接入列表',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const IntegrationInstanceListStory: Story = {
  name: '接入列表',
  render: () => <IntegrationInstanceList />,
};
