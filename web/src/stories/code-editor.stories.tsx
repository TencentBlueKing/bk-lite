import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import CodeEditor from '@/components/code-editor';

const meta: Meta<typeof CodeEditor> = {
  component: CodeEditor,
  title: 'Framework/Editors/CodeEditor',
  parameters: {
    docs: {
      description: {
        component:
          'Use `CodeEditor` only for genuine editing workflows or editor-specific interactions such as fullscreen editing, inline changes, and loading state. Read-only copy-and-run output should prefer `CodeSnippet`.',
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 760, padding: 16, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof CodeEditor>;

export const ShellCommand: Story = {
  args: {
    mode: 'shell',
    theme: 'monokai',
    name: 'shell-command',
    width: '100%',
    height: '160px',
    readOnly: true,
    value: `kubectl apply -f bk-lite-collector.yaml
kubectl rollout status deployment/bk-lite-collector -n bk-lite`,
    headerOptions: {
      copy: true,
      fullscreen: true,
    },
  },
};

export const TomlConfig: Story = {
  args: {
    ...ShellCommand.args,
    mode: 'toml',
    name: 'toml-config',
    value: `[inputs.prometheus]
urls = ["http://127.0.0.1:9090/metrics"]
interval = "30s"`,
  },
};

export const LoadingReadonly: Story = {
  args: {
    ...ShellCommand.args,
    name: 'loading-shell-command',
    loading: true,
  },
};

export const EditableTomlConfig: Story = {
  render: () => {
    const [value, setValue] = useState(`[inputs.snmp]
agents = ["udp://10.0.0.21:161"]
version = 2
community = "public"`);

    return (
      <CodeEditor
        mode="toml"
        theme="monokai"
        name="editable-toml-config"
        width="100%"
        height="260px"
        value={value}
        onChange={(nextValue?: string) => setValue(nextValue || '')}
        headerOptions={{
          copy: true,
          fullscreen: true,
        }}
        setOptions={{ showPrintMargin: false, useWorker: false }}
      />
    );
  },
  parameters: {
    docs: {
      description: {
        story:
          'Represents a true editor surface where users actively modify configuration content before saving, such as monitor SNMP collect templates.',
      },
    },
  },
};

export const EditableTemplateWithLoading: Story = {
  args: {
    mode: 'python',
    theme: 'monokai',
    name: 'editable-template-with-loading',
    width: '100%',
    height: '220px',
    value: `collector:
  name: disk-collector
  interval: 30
  endpoint: ${'{HOST_IP}'}`,
    loading: true,
    headerOptions: {
      copy: true,
      fullscreen: true,
    },
  },
  parameters: {
    docs: {
      description: {
        story:
          'Covers editor surfaces that remain editable in principle but may temporarily show loading while helper metadata or variable references are being prepared.',
      },
    },
  },
};

export const LegacyShowCopyAlias: Story = {
  args: {
    mode: 'python',
    theme: 'monokai',
    name: 'legacy-show-copy',
    width: '100%',
    height: '180px',
    readOnly: true,
    value: `def healthcheck():
    return "ok"`,
    showCopy: true,
  },
  parameters: {
    docs: {
      description: {
        story:
          'Covers legacy runtime callers that still enable copy actions via `showCopy` while newer shared usage prefers `headerOptions`.',
      },
    },
  },
};
