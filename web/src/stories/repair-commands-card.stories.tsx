import type { Meta, StoryObj } from '@storybook/nextjs';
import RepairCommandsCard from '@/app/opspilot/components/custom-chat-sse/RepairCommandsCard';

const meta: Meta<typeof RepairCommandsCard> = {
  component: RepairCommandsCard,
  title: 'OpsPilot/RepairCommandsCard',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#f5f5f5' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof RepairCommandsCard>;

export const Default: Story = {
  args: {
    commands: {
      commands_id: 'repair-1',
      received_at: Date.now(),
      commands_markdown: `**Update deployment**

\`\`\`bash
kubectl -n default set resources deployment/nginx-web \\
  --limits=cpu=500m,memory=512Mi \\
  --requests=cpu=200m,memory=256Mi
\`\`\`

**Apply probe patch**

\`\`\`bash
kubectl -n default patch deployment nginx-web --type='merge' -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "nginx",
          "readinessProbe": {
            "httpGet": { "path": "/healthz", "port": 8080 },
            "initialDelaySeconds": 5,
            "periodSeconds": 10
          }
        }]
      }
    }
  }
}'
\`\`\``,
    },
  },
};

export const SingleSection: Story = {
  args: {
    commands: {
      commands_id: 'repair-2',
      received_at: Date.now(),
      commands_markdown: `**Restart workload**

\`\`\`bash
kubectl rollout restart deployment api-server -n prod
\`\`\``,
    },
  },
};
