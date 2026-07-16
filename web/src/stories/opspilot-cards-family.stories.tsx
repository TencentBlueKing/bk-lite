import type { Meta, StoryObj } from '@storybook/nextjs';
import EntityCard from '@/components/opspilot-entity-card';
import SectionHeader from '@/components/section-header';
import SkillCard from '@/components/opspilot-skill-card';
import StudioCard from '@/components/opspilot-studio-card';

const entityCardArgs = {
  id: '1',
  name: 'Smart Assistant',
  introduction: 'An AI-powered assistant for operations and maintenance tasks.',
  created_by: 'admin',
  team_name: 'Default',
  team: [{ id: 1, name: 'Default' }],
  redirectUrl: '#',
  iconTypeMapping: ['jiqiren2', 'Bot'] as [string, string],
  onMenuClick: () => undefined,
};

const skillCardArgs = {
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
  onMenuClick: () => undefined,
};

const studioCardArgs = {
  id: 201,
  index: 0,
  name: 'Incident Copilot',
  introduction: 'Coordinates incident workflows, approvals, and operational follow-up across teams.',
  created_by: 'admin',
  team_name: ['SRE'],
  team: ['SRE'],
  online: true,
  bot_type: 1,
  is_pinned: false,
  permissions: ['View', 'Edit', 'Delete'],
  onMenuClick: () => undefined,
};

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Base card contract"
          description="EntityCard provides the shared browsing shell for OpsPilot assets: media banner, icon area, descriptive summary, metadata pills, and menu actions."
        />

        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <div style={{ width: 320 }}>
            <EntityCard
              {...entityCardArgs}
            />
          </div>

          <div style={{ width: 320 }}>
            <EntityCard
              {...entityCardArgs}
              online
              modelName="GPT-4o"
            />
          </div>

          <div style={{ width: 320 }}>
            <EntityCard
              {...entityCardArgs}
              skillType="Q&A"
              skill_type={1}
            />
          </div>

          <div style={{ width: 320 }}>
            <EntityCard
              {...entityCardArgs}
              showPinButton
              is_pinned
            />
          </div>

          <div style={{ width: 320 }}>
            <EntityCard
              {...entityCardArgs}
              team_name={['Team Alpha', 'Team Beta', 'Team Gamma']}
              team={[
                { id: 1, name: 'Team Alpha' },
                { id: 2, name: 'Team Beta' },
                { id: 3, name: 'Team Gamma' },
              ]}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Specialized card variants"
          description="SkillCard and StudioCard both reuse the same base shell while contributing their own business semantics for model, skill type, online state, and bot type."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <SkillCard {...skillCardArgs} />
            </div>
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <SkillCard
                {...skillCardArgs}
                name="Runbook Q&A"
                introduction="Answers questions from curated operations knowledge bases."
                skill_type={2}
                is_pinned
              />
            </div>
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <SkillCard
                {...skillCardArgs}
                name="Incident Planner"
                skill_type={3}
                llm_model_name="deepseek-reasoner"
              />
            </div>
          </div>

          <div className="space-y-4">
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <StudioCard {...studioCardArgs} />
            </div>
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <StudioCard
                {...studioCardArgs}
                name="Knowledge Desk"
                online={false}
                bot_type={2}
                team_name={['Knowledge']}
                team={['Knowledge']}
              />
            </div>
            <div style={{ width: 340, padding: 16, background: 'var(--color-fill-1)' }}>
              <StudioCard
                {...studioCardArgs}
                name="Runbook Flow"
                bot_type={3}
                is_pinned
                team_name={['Ops', 'Platform']}
                team={['Ops', 'Platform']}
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsPilot/Cards/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 920, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
