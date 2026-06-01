import type { Meta, StoryObj } from '@storybook/nextjs';
import BrowserStepProgress from '@/app/opspilot/components/custom-chat-sse/BrowserStepProgress';
import type { BrowserStepProgressData } from '@/app/opspilot/types/global';

const meta: Meta<typeof BrowserStepProgress> = {
  component: BrowserStepProgress,
  title: 'OpsPilot/BrowserStepProgress',
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 760, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof BrowserStepProgress>;

const baseSteps: BrowserStepProgressData[] = [
  {
    step_number: 1,
    max_steps: 3,
    url: 'https://kubernetes.io/docs/concepts/workloads/controllers/deployment/',
    title: 'Deployments | Kubernetes',
    thinking: 'Open the official deployment documentation first.',
    evaluation: 'Page loaded successfully.',
    memory: 'Need to compare the recommended probe settings later.',
    next_goal: 'Locate health probe guidance.',
    actions: [{ navigate: { url: 'https://kubernetes.io/docs/concepts/workloads/controllers/deployment/' } }],
    has_screenshot: false,
  },
  {
    step_number: 2,
    max_steps: 3,
    url: 'https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/',
    title: 'Configure Liveness, Readiness and Startup Probes',
    thinking: 'This page should contain the readiness/liveness examples I need.',
    evaluation: 'Found the relevant section for readinessProbe.',
    memory: 'Probe examples use /healthz and reasonable intervals.',
    next_goal: 'Capture screenshot evidence for the user.',
    actions: [
      { click: { index: 3 } },
      { scroll: { direction: 'down', amount: 600 } },
      { screenshot: true },
    ],
    has_screenshot: true,
    screenshot:
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0bkAAAAASUVORK5CYII=',
  },
];

export const Running: Story = {
  args: {
    history: {
      steps: [
        ...baseSteps,
        {
          step_number: 3,
          max_steps: 3,
          url: 'https://example.com/internal-runbook',
          title: 'Internal Runbook',
          thinking: 'Compare internal standards with upstream docs.',
          evaluation: '',
          memory: '',
          next_goal: 'Draft final recommendation.',
          actions: [{ input: { index: 2, text: 'readiness probe best practices' } }],
          has_screenshot: false,
        },
      ],
      isRunning: true,
    },
  },
};

export const Completed: Story = {
  args: {
    history: {
      steps: baseSteps,
      isRunning: false,
    },
  },
};
