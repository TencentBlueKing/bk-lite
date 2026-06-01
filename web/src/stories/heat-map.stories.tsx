import type { Meta, StoryObj } from '@storybook/react';
import EventHeatMap from '@/components/heat-map';

const meta: Meta<typeof EventHeatMap> = {
  component: EventHeatMap,
  title: 'Components/EventHeatMap',
};

export default meta;

type Story = StoryObj<typeof EventHeatMap>;

const generateMockData = () => {
  const data = [];
  const now = new Date();
  for (let i = 0; i < 30; i++) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    for (let hour = 0; hour < 24; hour++) {
      if (Math.random() > 0.7) {
        const eventDate = new Date(date);
        eventDate.setHours(hour, 0, 0, 0);
        data.push({
          event_time: eventDate.toISOString(),
          level: Math.random() > 0.5 ? 'warning' : 'critical',
        });
      }
    }
  }
  return data;
};

export const Default: Story = {
  args: {
    data: generateMockData(),
  },
};

export const Empty: Story = {
  args: {
    data: [],
  },
};
