import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Radio, Segmented, Select } from 'antd';
import DashboardWorkspaceHeader from '@/components/dashboard-workspace-header';
import DetailLayoutShell from '@/components/detail-layout-shell';
import IntroductionTableWorkspaceShell from '@/components/introduction-table-workspace-shell';
import ManagementTableShell from '@/components/management-table-shell';
import PageStatus from '@/components/page-status';
import PageFormHeaderCard from '@/components/page-form-header-card';
import PageFormWorkspaceShell from '@/components/page-form-workspace-shell';
import PageHeaderShell from '@/components/page-header-shell';
import PageIntroHeader from '@/components/page-intro-header';
import PageLayout from '@/components/page-layout';
import PanelShell from '@/components/panel-shell';
import RedirectToFirstMenu from '@/components/redirect-menu';
import RoutedDetailLayoutShell from '@/components/routed-detail-layout-shell';
import ResizableSidebar from '@/components/resizable-sidebar';
import SectionHeader from '@/components/section-header';
import SideMenu from '@/components/layout/sub-layout/side-menu';
import SummaryDetailLayoutShell from '@/components/summary-detail-layout-shell';
import TopMenu from '@/components/top-menu';
import TreeWorkspaceShell from '@/components/tree-workspace-shell';
import WithSideMenuLayout from '@/components/layout/sub-layout';
import TimeSelector from '@/components/time-selector';
import TopSection from '@/components/top-section';
import WorkspacePanel from '@/components/workspace-panel';

const FamilyOverview = () => {
  const workspaceColumns = [
    { title: 'Operator', dataIndex: 'operator', key: 'operator', width: 160 },
    { title: 'Module', dataIndex: 'module', key: 'module', width: 180 },
    { title: 'Summary', dataIndex: 'summary', key: 'summary', width: 320 },
  ];

  const workspaceDataSource = [
    { id: '1', operator: 'alice', module: 'Alarm settings', summary: 'Created a new shield strategy' },
    { id: '2', operator: 'bob', module: 'CMDB', summary: 'Exported change records' },
  ];

  const sideNavigationMenuItems = [
    { title: 'Overview', url: '/overview', name: 'overview', icon: 'home', operation: ['View'] } as any,
    { title: 'Configuration', url: '/configuration', name: 'configuration', icon: 'tool', operation: ['View'] } as any,
    { title: 'History', url: '/history', name: 'history', icon: 'dashboard', operation: ['View'] } as any,
  ];

  const managementTableColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Description', dataIndex: 'description', key: 'description' },
  ];

  const managementTableDataSource = [
    { id: 1, name: 'Team quota', description: 'Shared workspace quota rule' },
    { id: 2, name: 'Data source', description: 'Application data permission group' },
  ];

  const treeData = [
    {
      key: 'category-a',
      title: 'Category A',
      children: [
        { key: 'a-1', title: 'Item A-1', label: 'Item A-1', children: [] },
        { key: 'a-2', title: 'Item A-2', label: 'Item A-2', children: [] },
      ],
    },
    {
      key: 'category-b',
      title: 'Category B',
      children: [
        { key: 'b-1', title: 'Item B-1', label: 'Item B-1', children: [] },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Page scaffold" titleClassName="text-sm font-semibold" />
        <div className="h-[420px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <PageLayout
            height="100%"
            topSection={(
              <TopSection
                title="Application Settings"
                content="Manage page-level structure, permissions, and common actions with the shared layout vocabulary."
                iconType="tool"
              />
            )}
            leftSection={(
              <div className="w-full space-y-3">
                <SectionHeader spacing="flush" title="Navigation" titleClassName="text-sm font-semibold" />
                <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-sm">Overview</div>
                <div className="rounded-md px-3 py-2 text-sm text-[var(--color-text-2)]">Permissions</div>
                <div className="rounded-md px-3 py-2 text-sm text-[var(--color-text-2)]">Audit Log</div>
              </div>
            )}
            rightSection={(
              <PanelShell
                className="h-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)]"
                headerClassName="border-b border-[var(--color-border)] px-4 py-3"
                bodyClassName="space-y-3 p-4"
                footerClassName="border-t border-[var(--color-border)] px-4 py-3"
                header={(
                  <SectionHeader
                    spacing="flush"
                    title="Shared content panel"
                    titleClassName="text-sm font-medium"
                  />
                )}
                footer={(
                  <div className="flex gap-2">
                    <Button type="primary">Save</Button>
                    <Button>Cancel</Button>
                  </div>
                )}
              >
                <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                  The page scaffold keeps top summary, left navigation, and main work area aligned across apps.
                </div>
                <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                  Inner work surfaces then reuse `PanelShell` instead of inventing local card-like wrappers.
                </div>
              </PanelShell>
            )}
          />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Header shell" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <PageHeaderShell
              className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-6 py-4"
              title="Monitor Detail"
              subtitle="Inspect the current health of the selected instance and switch between governed views."
              leading={<Button type="text" icon={<ArrowLeftOutlined />} className="p-1!" />}
              subtitleLeading={(
                <span className="invisible p-1!">
                  <ArrowLeftOutlined />
                </span>
              )}
              actions={(
                <div className="flex items-center gap-2">
                  <Button>Cancel</Button>
                  <Button type="primary" icon={<PlusOutlined />}>
                    Add Widget
                  </Button>
                </div>
              )}
            />

            <PageHeaderShell
              className="rounded-xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3.5 py-2.5"
              style={{ boxShadow: '0 8px 22px rgba(31, 63, 104, 0.05)' }}
              headerRowClassName="flex items-center justify-between gap-4"
              contentClassName="min-w-0 flex-1 mr-6"
              titleRowClassName="flex items-center gap-3"
              titleClassName="m-0 text-xl leading-7 font-semibold text-[var(--color-text-1)]"
              subtitleClassName="m-0 text-sm leading-5 text-[var(--color-text-2)]"
              actionsClassName="flex shrink-0 items-center gap-1.5"
              title="Analysis View"
              subtitle="Shared header shell also supports elevated toolbars without forking a new layout primitive."
              actions={(
                <div className="flex items-center gap-1.5">
                  <Button type="text" size="small" icon={<EditOutlined />} />
                  <Button type="text" size="small" icon={<DeleteOutlined />} danger />
                </div>
              )}
            />

            <PageHeaderShell
              className="max-w-[520px] rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-4 py-3"
              title="A very long governed page header title that should stay truncation-safe beside trailing actions without every consumer re-declaring content width classes"
              subtitle="The default contract keeps the content column shrinkable even when the action area is present."
              actions={(
                <Button type="primary" size="small">
                  Save
                </Button>
              )}
            />
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Form scaffold" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <PageFormHeaderCard
              title="Deploy playbook to production"
              description="Shared framed headers can host page-level actions without reintroducing page-local card markup."
              onBackClick={() => undefined}
              spacing="flush"
              headerRowClassName="flex items-center justify-between gap-4"
              titleClassName="m-0 text-lg font-medium text-[var(--color-text-1)]"
              actions={(
                <>
                  <Button danger>Stop</Button>
                  <Button type="primary">Retry</Button>
                </>
              )}
            />

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <PageFormWorkspaceShell
                title="Quick execution"
                description="The same page scaffold keeps form pages aligned around a governed header card and stable content panel."
                className="w-full"
                headerSpacing="compact"
                panelClassName="rounded-lg border border-dashed border-[var(--color-border)] shadow-none"
              >
                <Form layout="vertical" className="w-full">
                  <Form.Item label="Job name" required>
                    <Input placeholder="Enter a name" />
                  </Form.Item>
                  <Form.Item label="Content source" required>
                    <Radio.Group>
                      <Radio value="template">Template</Radio>
                      <Radio value="manual">Manual</Radio>
                    </Radio.Group>
                  </Form.Item>
                  <div className="border-t border-[var(--color-border-1)] pt-4">
                    <Button type="primary">Execute now</Button>
                  </div>
                </Form>
              </PageFormWorkspaceShell>
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Intro headers" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <PageIntroHeader
              title="Vendor Management"
              description="Search vendors, refresh the current catalog, and create new providers from the same governed page-intro contract."
              actions={(
                <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
                  <Input.Search allowClear enterButton placeholder="Search vendors" className="w-full sm:w-72 lg:w-80" />
                  <Button type="default">Refresh</Button>
                  <Button type="primary" icon={<PlusOutlined />}>
                    Add Vendor
                  </Button>
                </div>
              )}
            />

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
              <SectionHeader spacing="compact" title="Intro spacing rhythm" titleClassName="text-sm font-medium" />
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                  <PageIntroHeader
                    title="Default intro"
                    description="Shared page intros default to a 16px handoff into the primary content band."
                    titleClassName="m-0 text-[16px] font-medium text-[var(--color-text-1)]"
                    descriptionClassName="m-0 text-[12px] text-[var(--color-text-3)]"
                    descriptionRowClassName="mt-1"
                  />
                  <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-xs text-[var(--color-text-3)]">
                    Default spacing
                  </div>
                </div>

                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                  <PageIntroHeader
                    spacing="compact"
                    title="Compact intro"
                    description="Compact intros keep strategy-edit flows tighter when the form should begin almost immediately below the heading."
                    titleClassName="m-0 text-[16px] font-medium text-[var(--color-text-1)]"
                    descriptionClassName="m-0 text-[12px] text-[var(--color-text-3)]"
                    descriptionRowClassName="mt-1"
                  />
                  <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-xs text-[var(--color-text-3)]">
                    Compact spacing
                  </div>
                </div>
              </div>
            </div>

            <PageIntroHeader
              title="Edit Policy"
              spacing="compact"
              description={<span className="text-[12px] text-[var(--color-text-3)]">CPU saturation alert</span>}
              leading={(
                <button
                  type="button"
                  className="cursor-pointer p-0 text-[20px] text-[var(--color-primary)]"
                >
                  <ArrowLeftOutlined />
                </button>
              )}
              headerRowClassName="flex items-center gap-3"
              titleClassName="m-0 text-[16px] font-medium text-[var(--color-text-1)]"
              descriptionRowClassName="mt-0"
              descriptionClassName="m-0"
              actionsClassName="w-auto"
            />
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Workspace headings" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="rounded-2xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)]/95 p-4">
              <SectionHeader spacing="regular" title="Regular heading rhythm" titleClassName="text-sm font-semibold" />
              <div className="space-y-3">
                <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-sm text-[var(--color-text-2)]">
                  Use `spacing=&quot;regular&quot;` when a section title should hand off to content with a 16px gap.
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                    <SectionHeader spacing="flush" title="Flush" titleClassName="text-sm font-medium" />
                    <div className="text-xs text-[var(--color-text-3)]">0px handoff</div>
                  </div>
                  <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                    <SectionHeader spacing="regular" title="Regular" titleClassName="text-sm font-medium" />
                    <div className="text-xs text-[var(--color-text-3)]">16px handoff</div>
                  </div>
                  <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                    <SectionHeader spacing="compact" title="Compact" titleClassName="text-sm font-medium" />
                    <div className="text-xs text-[var(--color-text-3)]">12px handoff</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-2xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)]/95 px-4 py-3">
              <DashboardWorkspaceHeader title="Application Performance" />
            </div>

            <div className="overflow-x-auto rounded-2xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)]/95 px-4 py-3">
              <DashboardWorkspaceHeader
                title="Log Throughput Dashboard"
                controls={(
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex flex-none items-center">
                      <TimeSelector
                        defaultValue={{ selectValue: 15, rangePickerVaule: null }}
                        onChange={() => undefined}
                        onRefresh={() => undefined}
                        onFrequenceChange={() => undefined}
                      />
                    </div>
                    <Button>Save</Button>
                  </div>
                )}
              />
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Top sections and layout variants" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Default top section" titleClassName="text-sm font-medium" />
            <TopSection
              title="Skill Settings"
              content="Manage shared configuration, usage policies, and operational notes for the selected skill."
              iconType="tool"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Custom icon" titleClassName="text-sm font-medium" />
            <TopSection
              title="Channel Details"
              content="Review notification channel basics and recent configuration changes."
              icon={(
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-(--color-primary) text-sm font-semibold text-white">
                  CH
                </div>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Integration variant" titleClassName="text-sm font-medium" />
            <TopSection
              title="Kubernetes"
              content="Configure onboarding, review collection state, and inspect the integration details for this plugin."
              iconSrc="/assets/icons/kubernetes.svg"
              variant="integration"
            />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Right workspace only" titleClassName="text-sm font-medium" />
            <PageLayout
              rightSection={(
                <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-2)]">
                  Right workspace
                </div>
              )}
              height="260px"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Top + right" titleClassName="text-sm font-medium" />
            <PageLayout
              topSection={(
                <TopSection
                  title="Quota Overview"
                  content="Use the shared page layout shell when a page needs one governed top section and a single main workspace."
                />
              )}
              rightSection={(
                <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-2)]">
                  Right workspace
                </div>
              )}
              height="260px"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Top + left + right" titleClassName="text-sm font-medium" />
            <PageLayout
              topSection={(
                <TopSection
                  title="User Structure"
                  content="The same framework shell supports a top section, an optional left navigator, and one primary working area."
                />
              )}
              leftSection={<div className="text-sm text-[var(--color-text-2)]">Left navigation</div>}
              rightSection={(
                <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-2)]">
                  Right workspace
                </div>
              )}
              height="320px"
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Detail shell" titleClassName="text-sm font-semibold" />
          <DetailLayoutShell
            wrapperClassName="h-[420px]"
            topSection={(
              <TopSection
                title="Node Detail"
                content="Review summary, switch subviews, and keep detail pages within one governed shell."
              />
            )}
            intro={<div className="text-sm text-[var(--color-text-2)]">Entity summary block</div>}
            onBackButtonClick={() => undefined}
            customMenuItems={[
              { title: 'Overview', url: '/detail/overview', name: 'overview' } as any,
              { title: 'Settings', url: '/detail/settings', name: 'settings' } as any,
              { title: 'Logs', url: '/detail/logs', name: 'logs' } as any,
            ]}
          >
            <div className="rounded-md bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
              Detail content surface
            </div>
          </DetailLayoutShell>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Routed detail shell" titleClassName="text-sm font-semibold" />
          <RoutedDetailLayoutShell
            wrapperClassName="h-[420px]"
            pathname="/detail/logs"
            items={[
              {
                path: '/detail/settings',
                title: 'Settings',
                description: 'Configure this detail view.',
              },
              {
                path: '/detail/logs',
                title: 'Logs',
                description: 'Inspect recent activity and history.',
              },
            ]}
            fallback={{
              title: 'Settings',
              description: 'Configure this detail view.',
            }}
            intro={<div className="text-sm text-[var(--color-text-2)]">Entity summary block</div>}
            onBackButtonClick={() => undefined}
            customMenuItems={[
              { title: 'Settings', url: '/detail/settings', name: 'settings' } as any,
              { title: 'Logs', url: '/detail/logs', name: 'logs' } as any,
            ]}
          >
            <div className="rounded-md bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
              Routed content surface
            </div>
          </RoutedDetailLayoutShell>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Side navigation shell" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <div className="h-[320px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex h-full gap-4">
              <SideMenu
                menuItems={[
                  { title: 'Overview', url: '/overview', name: 'overview', icon: 'home', operation: ['View'] } as any,
                  { title: 'Configuration', url: '/configuration', name: 'configuration', icon: 'tool', operation: ['View'] } as any,
                  { title: 'History', url: '/history', name: 'history', icon: 'dashboard', operation: ['View'] } as any,
                ]}
                showBackButton={true}
                showProgress={true}
                taskProgressComponent={(
                  <div className="absolute inset-x-3 bottom-14 rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-2)]">
                    Task Progress
                  </div>
                )}
                onBackButtonClick={() => undefined}
              >
                <div className="text-sm text-[var(--color-text-1)]">Introduction Content</div>
              </SideMenu>

              <div className="flex-1 rounded-md bg-[var(--color-bg-1)] p-4 text-sm text-[var(--color-text-2)]">
                Shared side-navigation shells give detail pages a stable intro, menu area, progress slot, and back affordance without each app recreating them.
              </div>
            </div>
          </div>

          <div className="h-[320px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex h-full gap-4">
              <SideMenu
                menuItems={[
                  { title: 'Overview', url: '/overview', name: 'overview', icon: 'home', operation: ['View'] } as any,
                  { title: 'Relationships', url: '/relationships', name: 'relationships', icon: 'dashboard', operation: ['View'] } as any,
                ]}
                showBackButton={true}
                renderBeforeItem={(item) =>
                  item.name === 'relationships' ? (
                    <li className="mb-1 rounded-md border border-dashed border-[var(--color-border-2)] px-3 py-2 text-xs text-[var(--color-text-3)]">
                      Shortcut block
                    </li>
                  ) : null
                }
                renderAfterItem={(item) =>
                  item.name === 'relationships' ? (
                    <div className="ml-4 mb-2 border-b border-[var(--color-border-2)] pb-2 text-xs text-[var(--color-text-3)]">
                      Nested relation items can render after a governed menu item without splitting shell and nav-list into separate public contracts.
                    </div>
                  ) : null
                }
              >
                <div className="text-sm text-[var(--color-text-1)]">Extended intro content</div>
              </SideMenu>

              <div className="flex-1 rounded-md bg-[var(--color-bg-1)] p-4 text-sm text-[var(--color-text-2)]">
                Extension blocks stay governed inside the shared `SideMenu` contract, so `SideMenuShell` and `SideMenuNavList` do not need standalone Storybook roots.
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Outer layout shell" titleClassName="text-sm font-medium" />
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="h-[320px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
                <WithSideMenuLayout
                  intro={<div className="text-sm text-[var(--color-text-1)]">Introduction Content</div>}
                  showBackButton
                  onBackButtonClick={() => undefined}
                  topSection={<div className="text-sm text-[var(--color-text-2)]">Top Section Content</div>}
                  showProgress
                  taskProgressComponent={(
                    <div className="rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-2)]">
                      Task Progress Placeholder
                    </div>
                  )}
                  customMenuItems={sideNavigationMenuItems}
                >
                  <div className="rounded-md bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
                    Shared side-menu layout keeps intro, menu column, optional top section, and main content framing aligned across routed pages.
                  </div>
                </WithSideMenuLayout>
              </div>

              <div className="h-[320px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
                <WithSideMenuLayout
                  showSideMenu={false}
                  layoutType="segmented"
                  pagePathName="/configuration"
                  customMenuItems={sideNavigationMenuItems}
                >
                  <div className="rounded-md bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
                    The same layout contract can switch to segmented navigation without opening a second public Storybook root for the outer shell.
                  </div>
                </WithSideMenuLayout>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Resizable sidebar contract" titleClassName="text-sm font-semibold" />
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="mb-3 text-sm text-[var(--color-text-2)]">
            The same governed sidebar-resize contract powers tree workspaces and monitor dashboards without each app rebuilding drag, collapse, and width persistence behavior.
          </div>

          <div className="h-[320px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
            <div className="flex h-full">
              <ResizableSidebar
                storageKey="storybook.layout.sidebar.width"
                collapseStorageKey="storybook.layout.sidebar.collapsed"
                defaultWidth={240}
                minWidth={180}
                maxWidth={320}
              >
                <div className="flex h-full flex-col gap-3 bg-[var(--color-bg-1)] p-3">
                  <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-sm font-medium text-[var(--color-text-1)]">
                    Asset tree
                  </div>
                  <div className="rounded-md px-3 py-2 text-sm text-[var(--color-text-2)]">Compute / Kubernetes</div>
                  <div className="rounded-md px-3 py-2 text-sm text-[var(--color-text-2)]">Database / PostgreSQL</div>
                  <div className="rounded-md px-3 py-2 text-sm text-[var(--color-text-2)]">Network / Switches</div>
                </div>
              </ResizableSidebar>

              <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-r-lg border-l border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-md bg-[var(--color-bg-1)] px-3 py-2 text-sm font-medium text-[var(--color-text-1)]">
                  Detail surface
                </div>
                <div className="rounded-md bg-[var(--color-bg-1)] p-3 text-sm text-[var(--color-text-2)]">
                  Drag the divider to resize. Collapse and restore stay inside the shared contract instead of leaking page-local sidebar logic into monitor and CMDB pages.
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Page status shell" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <PageStatus
              code="404"
              title="Page not found"
              description="Shared page-status layout keeps global 404, permission denial, and route-level missing-page states visually aligned."
              actionHref="/"
              actionLabel="Back to home"
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <PageStatus
                code="403"
                title="No permission"
                description="You do not have access to this page or feature."
                actionHref="/"
                actionLabel="Back to home"
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <PageStatus
                title="Professional dashboard not found"
                description="The selected dashboard key does not map to a registered professional dashboard."
                actionHref="/"
                actionLabel="Back to home"
              />
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Table workspace wrappers" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <IntroductionTableWorkspaceShell
                title="Workspace title"
                message="A framework shell for pages like alarm settings and CMDB operation logs that pair an introduction card with a governed table workspace."
                searchProps={{
                  allowClear: true,
                  className: 'w-[250px]',
                  enterButton: false,
                  placeholder: 'Search items',
                }}
                actions={<Button type="primary">Add item</Button>}
                columns={workspaceColumns}
                dataSource={workspaceDataSource}
                rowKey="id"
                pagination={{ current: 1, total: 2, pageSize: 20 }}
                scroll={{ y: 300, x: 'max-content' }}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <WorkspacePanel
                className="flex min-h-[280px] flex-col"
                toolbar={(
                  <div className="flex items-center justify-between gap-3">
                    <Input.Search allowClear placeholder="Search workspace items" className="w-64" />
                    <Button type="primary">Add Item</Button>
                  </div>
                )}
              >
                <div className="flex-1 rounded-md border border-[var(--color-border)] p-3 text-sm text-[var(--color-text-2)]">
                  Table or form content area
                </div>
              </WorkspacePanel>
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader
            spacing="flush"
            title="Framework workflow shells"
            titleClassName="text-sm font-semibold"
            description="Management, summary-detail, and tree workspace shells are governed here as reusable framework contracts instead of fragmenting the layout taxonomy into extra Storybook roots."
          />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="compact" title="ManagementTableShell" titleClassName="text-sm font-medium" />
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="min-h-[360px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <ManagementTableShell
                    topSection={(
                      <TopSection
                        title="Quota management"
                        content="The same management shell can own the page-level intro, governed search surface, and modal slot."
                      />
                    )}
                    searchProps={{
                      placeholder: 'Search',
                      onSearch: () => undefined,
                    }}
                    actions={<Button type="primary">Add</Button>}
                    columns={managementTableColumns}
                    dataSource={managementTableDataSource}
                    rowKey="id"
                    pagination={{
                      current: 1,
                      pageSize: 10,
                      total: 2,
                      onChange: () => undefined,
                    }}
                    scroll={{ y: 240 }}
                    modal={(
                      <div className="mb-4 rounded-md border border-dashed border-[var(--color-border)] p-3 text-sm text-[var(--color-text-2)]">
                        Modal branches stay page-local while the shell owns toolbar and table framing.
                      </div>
                    )}
                  />
                </div>

                <div className="min-h-[360px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <ManagementTableShell
                    toolbarContainerVariant="divided"
                    toolbar={(
                      <div className="flex flex-wrap items-center gap-2">
                        <Input.Search allowClear className="w-48" placeholder="Operator" />
                        <Select
                          allowClear
                          className="w-40"
                          options={[
                            { label: 'System Manager', value: 'system-manager' },
                            { label: 'Alarm', value: 'alarm' },
                          ]}
                          placeholder="Module"
                        />
                        <TimeSelector
                          clearable
                          defaultValue={{
                            selectValue: 7 * 24 * 60,
                            rangePickerVaule: null,
                          }}
                          onlyTimeSelect
                          showTime
                        />
                        <Button type="primary">Search</Button>
                        <Button>Reset</Button>
                      </div>
                    )}
                    columns={managementTableColumns}
                    dataSource={managementTableDataSource}
                    rowKey="id"
                    pagination={{
                      current: 1,
                      pageSize: 10,
                      total: 2,
                      onChange: () => undefined,
                    }}
                    scroll={{ y: 240 }}
                    rowSelection={{
                      selectedRowKeys: [1],
                      onChange: () => undefined,
                    }}
                  >
                    <div className="mt-4 rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                      Audit-log and batch-action variants stay inside the same framework shell contract.
                    </div>
                  </ManagementTableShell>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="compact" title="SummaryDetailLayoutShell" titleClassName="text-sm font-medium" />
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <SummaryDetailLayoutShell
                    topSection={(
                      <TopSection
                        title="Knowledge Documents"
                        content="The summary-detail shell keeps summary intro and routed detail content aligned across apps."
                      />
                    )}
                    summary={{
                      title: 'Production Runbook Library',
                      description: 'Shared operational knowledge base for internal runbooks and troubleshooting material.',
                    }}
                    onBackButtonClick={() => undefined}
                    customMenuItems={[
                      {
                        title: 'Documents',
                        url: '/opspilot/knowledge/detail/documents',
                        icon: 'shujuguanli',
                        name: 'knowledge_documents',
                        operation: [],
                      },
                      {
                        title: 'Testing',
                        url: '/opspilot/knowledge/detail/testing',
                        icon: 'ceshi',
                        name: 'knowledge_testing',
                        operation: [],
                      },
                    ]}
                  >
                    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
                      Horizontal summary variant
                    </div>
                  </SummaryDetailLayoutShell>
                </div>

                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <SummaryDetailLayoutShell
                    topSection={(
                      <TopSection
                        title="Package Management"
                        content="Vertical summary and progress branches stay inside the same shared detail workflow shell."
                      />
                    )}
                    summary={{
                      title: 'Collector Agent',
                      iconType: 'caijiqizongshu',
                      layout: 'vertical',
                      align: 'center',
                    }}
                    onBackButtonClick={() => undefined}
                    showProgress
                    taskProgressComponent={(
                      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
                        Task progress component
                      </div>
                    )}
                  >
                    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
                      Vertical summary with progress
                    </div>
                  </SummaryDetailLayoutShell>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="compact" title="TreeWorkspaceShell" titleClassName="text-sm font-medium" />
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="min-h-[360px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <TreeWorkspaceShell
                    treePanelProps={{
                      data: treeData,
                      defaultSelectedKey: 'a-1',
                      onNodeSelect: () => undefined,
                      surface: 'panel',
                      style: { width: 236, height: 'calc(100vh - 146px)' },
                    }}
                    contentClassName="w-[calc(100vw-236px)] min-w-[520px] bg-[var(--color-bg-1)] p-5"
                  >
                    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      Fixed sidebar workspace content
                    </div>
                  </TreeWorkspaceShell>
                </div>

                <div className="min-h-[360px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                  <TreeWorkspaceShell
                    sidebarMode="resizable"
                    collapseStorageKey="storybook.layoutFamily.treeWorkspace"
                    sidebarHeader={(
                      <PageHeaderShell
                        className="mb-[15px] px-2.5 pt-5"
                        title="Sidebar title"
                        as="h3"
                        headerRowClassName="flex items-center justify-between gap-3"
                        titleRowClassName="flex items-center"
                        titleClassName="m-0 text-sm font-semibold text-[var(--color-text-1)]"
                        actions={(
                          <Button size="small" type="primary">
                            Add
                          </Button>
                        )}
                      />
                    )}
                    sidebarContentClassName="h-[calc(100vh-146px)] w-full overflow-hidden bg-[var(--color-bg-1)]"
                    treeContainerClassName="flex-1 overflow-y-auto px-2.5 pb-2.5"
                    treePanelProps={{
                      data: treeData,
                      defaultSelectedKey: 'a-2',
                      onNodeSelect: () => undefined,
                    }}
                  >
                    <div className="space-y-4">
                      <PageHeaderShell
                        title="Resizable workspace"
                        as="h3"
                        headerRowClassName="flex items-center justify-between gap-3"
                        titleRowClassName="flex items-center"
                        titleClassName="m-0 text-sm font-medium text-[var(--color-text-1)]"
                        actions={<Button type="primary">Action</Button>}
                      />
                      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                        Resizable sidebar content
                      </div>
                    </div>
                  </TreeWorkspaceShell>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Section header contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Icon variants" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <SectionHeader title="Access Configuration" iconType="settings-fill" spacing="flush" />
              <SectionHeader
                title="Access Asset"
                icon={<InfoCircleOutlined className="text-lg text-[var(--color-text-2)]" />}
                spacing="flush"
              />
              <SectionHeader title="Login Settings" spacing="flush" />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Description + compact modes" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <SectionHeader
                title="Connection Values"
                description="Show the generated endpoint, headers, and other required fields for downstream configuration."
                variant="panel"
                spacing="flush"
              />
              <SectionHeader title="Base Information" variant="compact" spacing="flush" />
              <SectionHeader
                title="Verify status"
                icon={<InfoCircleOutlined className="text-lg text-[var(--color-primary)]" />}
                titleClassName="text-[var(--color-text-2)]"
                spacing="flush"
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Action surfaces" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <SectionHeader
                title="Chunk detail"
                titleClassName="text-sm font-medium text-[var(--color-text-1)]"
                actions={<Input.Search placeholder="Search" style={{ width: 180 }} allowClear />}
                spacing="flush"
              />
              <SectionHeader
                title="Results"
                actionsClassName="shrink-0"
                actions={(
                  <Segmented
                    size="small"
                    options={[
                      { label: 'Docs', value: 'docs' },
                      { label: 'QA', value: 'qa' },
                      { label: 'Graph', value: 'graph' },
                    ]}
                    value="docs"
                  />
                )}
                spacing="flush"
              />
              <SectionHeader
                title={(
                  <Input
                    autoFocus
                    value="Operations Console"
                    size="small"
                    className="w-48"
                    readOnly
                  />
                )}
                titleClassName="m-0 text-sm font-medium text-[var(--color-text-1)]"
                actions={(
                  <div className="flex items-center gap-2">
                    <Button size="small" type="text">Cancel</Button>
                    <Button size="small" type="primary">Save</Button>
                  </div>
                )}
                actionsClassName="flex items-center gap-2"
                spacing="flush"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="App shell header"
          titleClassName="text-sm font-semibold"
          description="`TopMenu` governs the global application header contract: branding, app switcher, notifications, user entry, and the optional primary navigation rail."
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div className="border-b border-[var(--color-border)] px-4 py-3 text-sm font-medium text-[var(--color-text-1)]">
              Full navigation
            </div>
            <TopMenu hideMainMenu={false} />
          </div>

          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div className="border-b border-[var(--color-border)] px-4 py-3 text-sm font-medium text-[var(--color-text-1)]">
              Header-only mode
            </div>
            <TopMenu hideMainMenu />
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Storybook structure" titleClassName="text-sm font-semibold" />
        <div className="text-sm text-[var(--color-text-2)]">
          The Layout family is governed through shared page-shell, section-header, detail, side-navigation, status, and configuration-workspace subtrees instead of separate leaf stories for every low-level header primitive.
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="First-menu redirect contract" titleClassName="text-sm font-semibold" />
        <div className="text-sm text-[var(--color-text-2)]">
          App landing pages mount <code className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs">RedirectToFirstMenu</code> to forward users to their first accessible menu entry. It is a side-effect component (renders <code className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs">null</code>) and is used by 10+ app entry pages (alarm, cmdb, monitor, log, opspilot, ops-analysis, node-manager, job, system-manager, and the root landing).
        </div>
        <div className="rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3 text-xs text-[var(--color-text-3)]">
          Demo note: the actual redirect is driven by the <code className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs">usePermissions</code> context. In Storybook, the component renders <code className="rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs">null</code> and performs no navigation, but the import path proves the contract.
          <div className="mt-2"><RedirectToFirstMenu /></div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Layout/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
