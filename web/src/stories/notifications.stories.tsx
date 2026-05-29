import type { Meta, StoryObj } from '@storybook/react';
import Notifications from '@/components/notifications';

const meta: Meta<typeof Notifications> = {
  component: Notifications,
  title: 'Components/Notifications',
  parameters: {
    mockData: [
      {
        url: '/api/proxy/notification/api/notification/unread_count/',
        method: 'GET',
        status: 200,
        response: { count: 3 },
      },
      {
        url: '/api/proxy/notification/api/notification/',
        method: 'GET',
        status: 200,
        response: {
          items: [
            { id: 1, notification_time: '2025-05-28T10:00:00Z', app_module: 'monitor', content: 'CPU usage exceeds 90% on server-01', is_read: false },
            { id: 2, notification_time: '2025-05-28T09:30:00Z', app_module: 'alarm', content: 'Disk space alert on db-master', is_read: false },
            { id: 3, notification_time: '2025-05-27T15:00:00Z', app_module: 'node_mgmt', content: 'Node agent disconnected: worker-03', is_read: true },
          ],
          count: 3,
        },
      },
    ],
  },
};

export default meta;

type Story = StoryObj<typeof Notifications>;

export const Default: Story = {};
