import { Meta, StoryObj } from '@storybook/nextjs';
import TimeSelector from '@/components/time-selector';
import dayjs from 'dayjs';

const meta: Meta<typeof TimeSelector> = {
  component: TimeSelector,
  title: 'Components/TimeSelector'
};
export default meta;

type Story = StoryObj<typeof TimeSelector>;

export const Default: Story = {
  args: {
    defaultValue: {
      selectValue: 15,
      rangePickerVaule: null,
    },
    onFrequenceChange: (frequency: number) => {
      console.log('Frequency changed:', frequency);
    },
    onRefresh: () => {
      console.log('Refresh clicked');
    },
  },
};

export const OnlyTimeSelect: Story = {
  args: {
    defaultValue: {
      selectValue: 15,
      rangePickerVaule: null,
    },
    onlyTimeSelect: true,
  },
};

export const OnlyRefresh: Story = {
  args: {
    onlyRefresh: true,
    onRefresh: () => {
      console.log('Refresh clicked');
    },
  },
};

export const CustomFrequencyList: Story = {
  args: {
    defaultValue: {
      selectValue: 15,
      rangePickerVaule: [dayjs().subtract(1, 'hour'), dayjs()],
    },
    customFrequencyList: [
      { label: '1s', value: 1 },
      { label: '5s', value: 5 },
      { label: '10s', value: 10 },
    ],
    onFrequenceChange: (frequency: number) => {
      console.log('Frequency changed:', frequency);
    },
  },
};

export const CustomTimeRangeList: Story = {
  args: {
    defaultValue: {
      selectValue: 15,
      rangePickerVaule: [dayjs().subtract(1, 'day'), dayjs()],
    },
    customTimeRangeList: [
      { label: 'Last 24 hours', value: 1440 },
      { label: 'Last 7 days', value: 10080 },
    ],
    onChange: (range: number[]) => {
      console.log('Selected time range:', range);
    },
  },
};
