import type { Meta, StoryObj } from '@storybook/nextjs';
import PortalConsolePreview from '@/app/system-manager/components/settings/PortalConsolePreview';

const meta = {
  title: 'System Manager/Settings/PortalConsolePreview',
  component: PortalConsolePreview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 920, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof PortalConsolePreview>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    portalName: 'BlueKing Lite',
    portalLogoUrl: '/app/systemLogo.png',
    portalFaviconUrl: '/logo-site.png',
    watermarkEnabled: false,
    watermarkText: '${portalName} · ${username} · ${date}',
  },
};

export const WithWatermark: Story = {
  args: {
    ...Default.args,
    watermarkEnabled: true,
    watermarkText: '${portalName} · ${username} · ${date}',
  },
};

export const InitialsFallback: Story = {
  args: {
    ...Default.args,
    portalName: 'Ops Console',
    portalLogoUrl: '',
    portalFaviconUrl: '',
  },
};
