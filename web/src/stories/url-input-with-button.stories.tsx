import type { Meta, StoryObj } from '@storybook/nextjs';
import UrlInputWithButton from '@/app/opspilot/components/tool/urlInputWithButton';

const meta = {
  title: 'OpsPilot/UrlInputWithButton',
  component: UrlInputWithButton,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 680, padding: 16, background: 'var(--color-bg)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof UrlInputWithButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    value: 'https://example.com/tools/openapi.json',
    placeholder: '请输入 OpenAPI 地址',
    fetchButtonText: '获取工具',
    onChange: () => {},
    onFetch: () => {},
  },
};

export const Loading: Story = {
  args: {
    ...Default.args,
    fetchLoading: true,
  },
};

export const Disabled: Story = {
  args: {
    ...Default.args,
    disabled: true,
  },
};
