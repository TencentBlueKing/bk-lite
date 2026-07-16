import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button } from 'antd';
import {
  DownloadOutlined,
  EditOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/components/app-view-fullscreen';
import OpsAnalysisDashboardEmptyState from '@/app/ops-analysis/components/ops-analysis-dashboard-empty-state';
import ViewToolbar from '@/app/ops-analysis/components/ops-analysis-view-toolbar';
import ViewToolbarEditActions from '@/app/ops-analysis/components/ops-analysis-view-toolbar/editActions';
import SectionHeader from '@/components/section-header';

const FullscreenCanvasDemo = () => {
  const { isFullscreen, enterFullscreen, exitFullscreen } = useAppViewFullscreen();

  return (
    <div
      style={{
        position: 'relative',
        width: isFullscreen ? '100vw' : '100%',
        height: isFullscreen ? '100vh' : 320,
        border: isFullscreen ? 'none' : '1px solid var(--color-border)',
        borderRadius: isFullscreen ? 0 : 8,
        overflow: 'hidden',
        background: 'var(--color-bg-1)',
      }}
    >
      <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
      <div className="flex h-full flex-col gap-3 p-4">
        <ViewToolbar
          title="Topology Canvas"
          description="The fullscreen affordance belongs to the ops-analysis view workflow, where shared toolbar actions and escape-to-exit behavior travel together."
          isBuiltIn={false}
          actions={(
            <div className="flex items-center gap-1.5">
              {!isFullscreen && (
                <Button
                  type="text"
                  icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
                  className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
                  onClick={enterFullscreen}
                />
              )}
            </div>
          )}
        />
        <div className="flex-1 rounded-lg border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-2)]" />
      </div>
    </div>
  );
};

const FamilyOverview = () => {
  const [isEditMode, setIsEditMode] = useState(false);

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="ViewToolbar shell" />
        <ViewToolbar
          title="Production Topology"
          description="Canvas actions and metadata stay aligned across ops-analysis views."
          isBuiltIn
          actions={
            <>
              <Button
                type="text"
                icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
                className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
              />
              <Button
                type="text"
                icon={<EditOutlined style={{ fontSize: 16 }} />}
                className="rounded-full!"
              />
            </>
          }
        />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="ViewToolbarEditActions states" />
        <div className="flex flex-wrap items-center gap-4">
          <ViewToolbarEditActions
            isEditMode={false}
            onEdit={() => setIsEditMode(true)}
            onSave={() => undefined}
            onCancel={() => setIsEditMode(false)}
            editButtonClassName="rounded-full!"
          />
          <ViewToolbarEditActions
            isEditMode={true}
            onEdit={() => undefined}
            onSave={() => setIsEditMode(false)}
            onCancel={() => setIsEditMode(false)}
            saveIcon={<SaveOutlined />}
            saveButtonClassName="rounded-full!"
            cancelButtonClassName="rounded-full!"
            editingActionsClassName="flex items-center gap-2"
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Combined family contract" />
        <ViewToolbar
          title="Architecture View"
          description="The toolbar shell and edit-action cluster travel together as one shared family."
          isBuiltIn={false}
          actions={
            <>
              <Button
                type="text"
                icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
                className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
              />
              <ViewToolbarEditActions
                isEditMode={isEditMode}
                onEdit={() => setIsEditMode(true)}
                onSave={() => setIsEditMode(false)}
                onCancel={() => setIsEditMode(false)}
                saveIcon={<SaveOutlined />}
                saveButtonClassName="rounded-full!"
                cancelButtonClassName="rounded-full!"
                editButtonClassName="rounded-full!"
                editingActionsClassName="ml-1.5 flex items-center gap-2"
              />
            </>
          }
        />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Dashboard variant" />
        <ViewToolbar
          title="Production Dashboard"
          description="Dashboard mode reuses the same shell and edit-action contract while keeping refresh, export, and add actions."
          isBuiltIn={false}
          className="mb-0 rounded-none border-x-0 border-t-0 px-4 py-2"
          style={{ boxShadow: 'none' }}
          titleClassName="text-base leading-6"
          descriptionClassName="mt-0.5 text-xs leading-4 text-[var(--color-text-3)]"
          actionsClassName="flex-wrap justify-end"
          actions={
            <div className="flex items-center gap-1.5">
              <Button
                type="text"
                icon={<ReloadOutlined style={{ fontSize: 16 }} />}
                className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
              />
              <Button
                type="text"
                icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
                className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
              />
              {!isEditMode && (
                <Button
                  type="text"
                  icon={<DownloadOutlined style={{ fontSize: 16 }} />}
                  className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
                />
              )}
              {isEditMode && (
                <>
                  <Button
                    type="text"
                    icon={<SettingOutlined style={{ fontSize: 16 }} />}
                    className="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
                  />
                  <Button type="default" icon={<PlusOutlined />} className="rounded-full!">
                    Add View
                  </Button>
                  <Button type="default" icon={<PlusOutlined />} className="rounded-full!">
                    Add Group
                  </Button>
                </>
              )}
              <ViewToolbarEditActions
                isEditMode={isEditMode}
                onEdit={() => setIsEditMode(true)}
                onSave={() => setIsEditMode(false)}
                onCancel={() => setIsEditMode(false)}
                saveIcon={<SaveOutlined />}
                saveButtonClassName="rounded-full!"
                cancelButtonClassName="rounded-full!"
                editButtonClassName="rounded-full! h-8 w-8 min-w-8 flex items-center justify-center"
                editingActionsClassName="ml-4 flex items-center gap-2"
              />
            </div>
          }
        />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Fullscreen canvas behavior" />
        <FullscreenCanvasDemo />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Dashboard empty-state workflow" />
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="rounded-[12px] border border-dashed border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4">
            <ViewToolbar
              title="Production Dashboard"
              description="When no views exist yet, the same dashboard toolbar contract still owns the primary Add View affordance and empty-canvas grammar."
              isBuiltIn={false}
              className="mb-0 rounded-none border-x-0 border-t-0 px-4 py-2"
              style={{ boxShadow: 'none' }}
              titleClassName="text-base leading-6"
              descriptionClassName="mt-0.5 text-xs leading-4 text-[var(--color-text-3)]"
              actionsClassName="flex-wrap justify-end"
              actions={(
                <div className="flex items-center gap-1.5">
                  <Button
                    type="default"
                    icon={<PlusOutlined />}
                    className="rounded-full!"
                  >
                    Add View
                  </Button>
                </div>
              )}
            />
            <div className="h-[280px]">
              <OpsAnalysisDashboardEmptyState
                description="Add the first view to start building the dashboard canvas."
                action={(
                  <Button type="primary" icon={<PlusOutlined aria-hidden="true" />}>
                    Add View
                  </Button>
                )}
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsAnalysis/ViewToolbar/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 980, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
