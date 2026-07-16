import type { Meta, StoryObj } from '@storybook/nextjs';
import { useState } from 'react';
import SectionHeader from '@/components/section-header';
import MenuGroupCard from '@/components/system-manager-application-menu/group-card';
import MenuPageCard from '@/components/system-manager-application-menu/page-card';
import SourceMenuTree from '@/components/system-manager-application-menu/source-menu-tree';
import MenuPageItem from '@/components/system-manager-menu-page-item';
import {
  systemManagerGroupPages,
  systemManagerMenuPage,
  systemManagerSourceMenus,
} from './system-manager-application-menu.fixtures';

const FamilyOverview = () => {
  const [isEditingPageItem, setIsEditingPageItem] = useState(false);
  const [pageItemName, setPageItemName] = useState(systemManagerMenuPage.display_name);

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Source menu selection states"
          titleClassName="text-sm font-semibold"
        />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-2">
            <SectionHeader spacing="flush" title="Default" titleClassName="text-xs font-medium" />
            <SourceMenuTree
              sourceMenus={[...systemManagerSourceMenus]}
              selectedKeys={['dashboard']}
              loading={false}
              onCheck={() => {}}
            />
          </div>
          <div className="space-y-2">
            <SectionHeader spacing="flush" title="Loading" titleClassName="text-xs font-medium" />
            <SourceMenuTree
              sourceMenus={[...systemManagerSourceMenus]}
              selectedKeys={['dashboard']}
              loading
              onCheck={() => {}}
            />
          </div>
          <div className="space-y-2">
            <SectionHeader spacing="flush" title="Disabled" titleClassName="text-xs font-medium" />
            <SourceMenuTree
              sourceMenus={[...systemManagerSourceMenus]}
              selectedKeys={['dashboard']}
              loading={false}
              disabled
              onCheck={() => {}}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="MenuGroupCard states" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <MenuGroupCard
            group={{
              id: 'monitoring',
              name: 'Monitoring',
              children: systemManagerGroupPages,
            }}
            isEditing={false}
            onDragStart={() => {}}
            onDragEnd={() => {}}
            onRename={() => {}}
            onEdit={() => {}}
            onDelete={() => {}}
            onCancelEdit={() => {}}
            onDropToGroup={() => {}}
            onRemovePage={() => {}}
            onRenamePage={() => {}}
            onPageDragStart={() => {}}
            onPageDragOver={() => {}}
            onPageDrop={() => {}}
          />
          <MenuGroupCard
            group={{
              id: 'monitoring',
              name: 'Monitoring',
              children: systemManagerGroupPages,
            }}
            isEditing
            onDragStart={() => {}}
            onDragEnd={() => {}}
            onRename={() => {}}
            onEdit={() => {}}
            onDelete={() => {}}
            onCancelEdit={() => {}}
            onDropToGroup={() => {}}
            onRemovePage={() => {}}
            onRenamePage={() => {}}
            onPageDragStart={() => {}}
            onPageDragOver={() => {}}
            onPageDrop={() => {}}
          />
          <MenuGroupCard
            group={{
              id: 'empty',
              name: 'Empty Group',
              children: [],
            }}
            isEditing={false}
            onDragStart={() => {}}
            onDragEnd={() => {}}
            onRename={() => {}}
            onEdit={() => {}}
            onDelete={() => {}}
            onCancelEdit={() => {}}
            onDropToGroup={() => {}}
            onRemovePage={() => {}}
            onRenamePage={() => {}}
            onPageDragStart={() => {}}
            onPageDragOver={() => {}}
            onPageDrop={() => {}}
          />
          <MenuGroupCard
            group={{
              id: 'monitoring',
              name: 'Monitoring',
              children: systemManagerGroupPages,
            }}
            isEditing={false}
            isDragging
            dragOverPageIndex={1}
            onDragStart={() => {}}
            onDragEnd={() => {}}
            onRename={() => {}}
            onEdit={() => {}}
            onDelete={() => {}}
            onCancelEdit={() => {}}
            onDropToGroup={() => {}}
            onRemovePage={() => {}}
            onRenamePage={() => {}}
            onPageDragStart={() => {}}
            onPageDragOver={() => {}}
            onPageDrop={() => {}}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="MenuPage primitives" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3">
            <SectionHeader spacing="flush" title="Card shell" titleClassName="text-xs font-medium" />
            <div style={{ maxWidth: 420 }}>
              <MenuPageCard
                page={systemManagerMenuPage}
                onDragStart={() => {}}
                onDragEnd={() => {}}
                onRemove={() => {}}
                onRename={() => {}}
              />
            </div>
          </div>

          <div className="space-y-3">
            <SectionHeader spacing="flush" title="Card without icon" titleClassName="text-xs font-medium" />
            <div style={{ maxWidth: 420 }}>
              <MenuPageCard
                page={{
                  ...systemManagerMenuPage,
                  icon: undefined,
                  display_name: 'Alert Policy',
                  originName: undefined,
                  url: '/monitor/alarm/policy',
                }}
                onDragStart={() => {}}
                onDragEnd={() => {}}
                onRemove={() => {}}
                onRename={() => {}}
              />
            </div>
          </div>

          <div className="space-y-3">
            <SectionHeader spacing="flush" title="Group row variant" titleClassName="text-xs font-medium" />
            <MenuPageItem
              page={systemManagerMenuPage}
              tempName={systemManagerMenuPage.display_name}
              setTempName={() => {}}
              isEditing={false}
              onSaveEdit={() => {}}
              onCancelEdit={() => {}}
              onStartEdit={() => {}}
              onRemove={() => {}}
              draggable
              variant="group"
            />
          </div>

          <div className="space-y-3">
            <SectionHeader spacing="flush" title="Inline editing" titleClassName="text-xs font-medium" />
            <MenuPageItem
              page={systemManagerMenuPage}
              tempName={pageItemName}
              setTempName={setPageItemName}
              isEditing={isEditingPageItem}
              onSaveEdit={() => setIsEditingPageItem(false)}
              onCancelEdit={() => setIsEditingPageItem(false)}
              onStartEdit={() => setIsEditingPageItem(true)}
              onRemove={() => {}}
              draggable={!isEditingPageItem}
              variant="card"
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/SystemManager/ApplicationMenu/FamilyOverview',
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
