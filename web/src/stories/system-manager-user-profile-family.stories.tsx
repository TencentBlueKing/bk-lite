import { useMemo, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import { Button, Segmented } from 'antd';
import SectionHeader from '@/components/section-header';
import UserInformation from '@/components/top-menu/user-info/userInformation';
import UserProfilePasswordModal from '@/components/top-menu/user-info/passwordModal';
import VersionModal from '@/components/top-menu/user-info/versionModal';
import {
  renderSystemManagerVersionContent,
  systemManagerStorybookPasswordPolicy,
  systemManagerStorybookUserInfo,
  systemManagerVersionContentMap,
} from './system-manager-user-profile.fixtures';

const FamilyOverview = () => {
  const [activeSurface, setActiveSurface] = useState<'information' | 'password' | 'version'>(
    'information',
  );

  const surfaceSummary = useMemo(() => ({
    information: {
      title: 'InformationDrawer',
      description:
        'Owns editable account profile fields, locale/timezone preferences, and nested verification flows.',
    },
    password: {
      title: 'PasswordModal',
      description:
        'Owns self-service password reset using the shared security password-form contract.',
    },
    version: {
      title: 'VersionModal',
      description:
        'Owns tabbed release-log browsing and markdown rendering for the current product surface.',
    },
  }), []);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="flex items-start justify-between gap-4">
          <SectionHeader
            className="mb-0 flex-1"
            title="UserProfile surfaces"
            titleClassName="text-sm font-semibold"
            description="Shared account-management components travel together through the top-menu user profile workflow."
          />

          <Segmented
            value={activeSurface}
            onChange={(value) =>
              setActiveSurface(value as 'information' | 'password' | 'version')
            }
            options={[
              { label: 'Information', value: 'information' },
              { label: 'Password', value: 'password' },
              { label: 'Version', value: 'version' },
            ]}
          />
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            title={surfaceSummary[activeSurface].title}
            titleClassName="text-sm font-semibold"
            description={surfaceSummary[activeSurface].description}
          />

          {activeSurface === 'information' ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <SectionHeader
                  spacing="compact"
                  title="Nested verification workflow"
                  titleClassName="text-sm font-semibold"
                  description="The information drawer owns two guarded entry points: change email first opens identity verification, then enters the email-code modal; change password follows the same verification gate before entering the password modal."
                />
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--color-text-3)]">
                  <span className="rounded-full bg-[var(--color-fill-1)] px-3 py-1">Change email</span>
                  <span className="rounded-full bg-[var(--color-fill-1)] px-3 py-1">Verify identity</span>
                  <span className="rounded-full bg-[var(--color-fill-1)] px-3 py-1">Send code</span>
                  <span className="rounded-full bg-[var(--color-fill-1)] px-3 py-1">Confirm new email</span>
                  <span className="rounded-full bg-[var(--color-fill-1)] px-3 py-1">Change password</span>
                </div>
              </div>

              <div style={{ height: 820 }}>
                <UserInformation
                  visible
                  onClose={() => undefined}
                  fetchUserInfoAction={async () => systemManagerStorybookUserInfo}
                  updateUserBaseInfoAction={async () => undefined}
                />
              </div>
            </div>
          ) : null}

          {activeSurface === 'password' ? (
            <UserProfilePasswordModal
              visible
              onCancel={() => undefined}
              onSuccess={() => undefined}
              fetchPolicyAction={async () => systemManagerStorybookPasswordPolicy}
              resetPasswordAction={async () => undefined}
            />
          ) : null}

          {activeSurface === 'version' ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <SectionHeader
                  spacing="compact"
                  title="Release notes available"
                  titleClassName="text-sm font-semibold"
                  description="The default version-history contract renders the governed markdown release browser when release files are present."
                />
                <VersionModal
                  visible
                  onClose={() => undefined}
                  fetchVersionFilesAction={async () => Object.keys(systemManagerVersionContentMap)}
                  renderVersionContent={renderSystemManagerVersionContent}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <SectionHeader
                  spacing="compact"
                  title="Empty release history"
                  titleClassName="text-sm font-semibold"
                  description="The same shared modal also owns the empty-state branch when no release-note files are available yet."
                />
                <VersionModal
                  visible
                  onClose={() => undefined}
                  fetchVersionFilesAction={async () => []}
                  renderVersionContent={renderSystemManagerVersionContent}
                />
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button size="small">InformationDrawer</Button>
          <Button size="small">PasswordModal</Button>
          <Button size="small">VersionModal</Button>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/SystemManager/UserProfile/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
