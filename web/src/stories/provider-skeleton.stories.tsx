import type { Meta, StoryObj } from '@storybook/nextjs';
import { ModelTreeSkeleton, ProviderGridSkeleton } from '@/app/opspilot/components/provider/skeleton';

const meta: Meta<typeof ProviderGridSkeleton> = {
  component: ProviderGridSkeleton,
  title: 'OpsPilot/ProviderSkeletons',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ProviderGridSkeleton>;

export const GridLoading: Story = {};

export const TreeLoading: Story = {
  render: () => (
    <div style={{ width: 320, height: 420 }}>
      <ModelTreeSkeleton />
    </div>
  ),
};
