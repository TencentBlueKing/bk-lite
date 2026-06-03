import type { Meta, StoryObj } from '@storybook/nextjs';
import ReportDownloadCard from '@/app/opspilot/components/custom-chat-sse/ReportDownloadCard';

const meta: Meta<typeof ReportDownloadCard> = {
  component: ReportDownloadCard,
  title: 'OpsPilot/ReportDownloadCard',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ReportDownloadCard>;

export const Default: Story = {
  args: {
    download: {
      download_id: 'download-1',
      filename: 'k8s-fix-report.docx',
      mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      content_base64: 'U2FtcGxlIHJlcG9ydCBjb250ZW50',
      received_at: Date.now(),
    },
  },
};

export const PdfReport: Story = {
  args: {
    download: {
      download_id: 'download-2',
      filename: 'ops-audit-summary.pdf',
      mime_type: 'application/pdf',
      content_base64: 'JVBERi0xLjQKJcfs...',
      received_at: Date.now(),
    },
  },
};
