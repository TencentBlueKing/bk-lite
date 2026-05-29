import type { Meta, StoryObj } from '@storybook/react';
import MarkdownRenderer from '@/components/markdown';

const meta: Meta<typeof MarkdownRenderer> = {
  component: MarkdownRenderer,
  title: 'Components/MarkdownRenderer',
};

export default meta;

type Story = StoryObj<typeof MarkdownRenderer>;

export const WithContent: Story = {
  args: {
    content: `# Hello World

This is a **markdown** renderer component.

## Features
- Supports GFM (GitHub Flavored Markdown)
- Code highlighting
- Tables

| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |

\`\`\`javascript
const hello = "world";
console.log(hello);
\`\`\`
`,
  },
};

export const Empty: Story = {
  args: {
    content: '',
  },
};
