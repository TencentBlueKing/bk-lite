import type { Meta, StoryObj } from '@storybook/react';
import EntityCard from '@/app/opspilot/components/entity-card';

const meta: Meta<typeof EntityCard> = {
  component: EntityCard,
  title: 'OpsPilot/EntityCard',
  decorators: [
    (Story) => (
      <div style={{ width: 320 }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof EntityCard>;

const baseArgs = {
  id: '1',
  name: 'Smart Assistant',
  introduction: 'An AI-powered assistant for operations and maintenance tasks.',
  created_by: 'admin',
  team_name: 'Default',
  team: [{ id: 1, name: 'Default' }],
  redirectUrl: '#',
  iconTypeMapping: ['jiqiren2', 'Bot'] as [string, string],
  onMenuClick: () => {},
};

export const Default: Story = {
  args: {
    ...baseArgs,
  },
};

export const Online: Story = {
  args: {
    ...baseArgs,
    online: true,
    modelName: 'GPT-4o',
  },
};

export const WithSkillType: Story = {
  args: {
    ...baseArgs,
    skillType: 'Q&A',
    skill_type: 1,
  },
};

export const Pinned: Story = {
  args: {
    ...baseArgs,
    is_pinned: true,
    showPinButton: true,
  },
};

export const MultipleTeams: Story = {
  args: {
    ...baseArgs,
    team_name: ['Team Alpha', 'Team Beta', 'Team Gamma'],
    team: [
      { id: 1, name: 'Team Alpha' },
      { id: 2, name: 'Team Beta' },
      { id: 3, name: 'Team Gamma' },
    ],
  },
};
