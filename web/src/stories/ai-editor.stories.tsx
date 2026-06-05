import type { Meta, StoryObj } from '@storybook/react';
import AIEditor from '@/app/opspilot/components/ai-editor';

const meta: Meta<typeof AIEditor> = {
  component: AIEditor,
  title: 'OpsPilot/AIEditor',
};

export default meta;

type Story = StoryObj<typeof AIEditor>;

export const Default: Story = {
  args: {
    placeholder: 'Start typing here...',
    style: { height: 300, border: '1px solid #d9d9d9', borderRadius: 8 },
  },
};

export const WithDefaultValue: Story = {
  args: {
    defaultValue: '# Hello World\n\nThis is a **rich text editor** powered by AiEditor.\n\n- Feature 1\n- Feature 2\n- Feature 3',
    style: { height: 400, border: '1px solid #d9d9d9', borderRadius: 8 },
  },
};
