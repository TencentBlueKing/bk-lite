import React from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import BlockResultItem from '@/app/opspilot/components/block-result';

const meta: Meta<typeof BlockResultItem> = {
  component: BlockResultItem,
  title: 'OpsPilot/BlockResultItem',
};

export default meta;

type Story = StoryObj<typeof BlockResultItem>;

const mockResult = {
  id: 1,
  name: 'Server Deployment Guide',
  content: 'To deploy the server, first ensure all environment variables are configured correctly. Run `make build` followed by `docker-compose up -d`. Monitor the logs with `docker logs -f server`.',
  knowledge_source_type: 'file',
  score: 0.9523,
};

export const Default: Story = {
  args: {
    result: mockResult,
    index: 0,
    onClick: () => {},
  },
};

export const WebPageSource: Story = {
  args: {
    result: {
      ...mockResult,
      id: 2,
      name: 'API Documentation',
      knowledge_source_type: 'web_page',
      score: 0.8741,
    },
    index: 1,
    onClick: () => {},
  },
};

export const ManualSource: Story = {
  args: {
    result: {
      ...mockResult,
      id: 3,
      name: 'FAQ Entry',
      content: 'How to reset password? Go to Settings > Security > Reset Password.',
      knowledge_source_type: 'manual',
      score: 0.7892,
    },
    index: 2,
    onClick: () => {},
  },
};

export const WithoutScore: Story = {
  args: {
    result: mockResult,
    index: 0,
    onClick: () => {},
    showScore: false,
  },
};

export const WithSlot: Story = {
  args: {
    result: mockResult,
    index: 0,
    onClick: () => {},
    slot: <span style={{ color: '#1890ff', cursor: 'pointer' }}>View Detail</span>,
  },
};
