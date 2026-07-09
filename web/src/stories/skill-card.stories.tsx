import type { Meta, StoryObj } from '@storybook/nextjs';
import SkillCard from '@/app/opspilot/components/skill/skillCard';

const baseArgs = {
  id: 101,
  index: 0,
  name: 'Kubernetes Diagnosis',
  introduction: 'Diagnoses workload configuration risks and suggests safe remediation steps.',
  created_by: 'admin',
  team_name: 'Default',
  team: ['Default'],
  llm_model_name: 'gpt-4o',
  skill_type: 1,
  is_pinned: false,
  permissions: ['View', 'Setting', 'Delete'],
  onMenuClick: () => {},
};

const meta = {
  title: 'OpsPilot/SkillCard',
  component: SkillCard,
  decorators: [
    (Story) => (
      <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SkillCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ToolSkill: Story = {
  args: baseArgs,
};

export const QASkill: Story = {
  args: {
    ...baseArgs,
    name: 'Runbook Q&A',
    introduction: 'Answers questions from curated operations knowledge bases.',
    skill_type: 2,
    is_pinned: true,
  },
};
