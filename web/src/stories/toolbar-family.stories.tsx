import React, { useRef, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import { Button, Dropdown, Input, Radio, Select, Segmented, Space, Typography } from 'antd';
import {
  DownOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import FilterToolbar from '@/components/filter-toolbar';
import RefreshIconButton from '@/components/refresh-icon-button';
import SearchActionBar from '@/components/search-action-bar';
import SearchCombination from '@/components/search-combination';
import SearchCombinationToolbar from '@/components/search-combination-toolbar';
import SelectableTagFilterGroup from '@/components/selectable-tag-filter-group';
import TimeSelector from '@/components/time-selector';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import type { TimeSelectorRef } from '@/types';

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Split toolbar contracts
        </div>
        <div className="grid gap-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolbarSplitShell
              leading={(
                <Radio.Group defaultValue="file">
                  <Radio.Button value="file">Local file (12)</Radio.Button>
                  <Radio.Button value="web">Web link (4)</Radio.Button>
                  <Radio.Button value="manual">Manual text (8)</Radio.Button>
                </Radio.Group>
              )}
              trailing={(
                <>
                  <Input.Search allowClear className="w-60" placeholder="Search knowledge source" />
                  <Button icon={<ReloadOutlined />} />
                  <Button type="primary" icon={<PlusOutlined />}>
                    Add source
                  </Button>
                  <Dropdown
                    menu={{
                      items: [
                        { key: 'train', label: 'Start training' },
                        { key: 'delete', label: 'Delete selected' },
                      ],
                    }}
                  >
                    <Button>
                      <Space>
                        Batch actions
                        <DownOutlined />
                      </Space>
                    </Button>
                  </Dropdown>
                </>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolbarSplitShell
              leading={<Input allowClear className="w-[240px]" placeholder="Search model" />}
              trailing={(
                <>
                  <Button type="primary">Add model</Button>
                  <Button>Add group</Button>
                  <Button icon={<SettingOutlined />}>Manage enum library</Button>
                </>
              )}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Search-led action bars
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SearchActionBar
              searchProps={{
                placeholder: 'Search',
              }}
              actions={(
                <>
                  <Button type="primary">Add</Button>
                  <Button>Batch Delete</Button>
                </>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SearchActionBar
              spacing="flush"
              className="justify-between"
              searchProps={{
                placeholder: 'Search metrics',
                className: 'w-[400px]',
                allowClear: true,
              }}
              actions={(
                <>
                  <Button type="primary">Add Group</Button>
                  <Button>Add Metric</Button>
                </>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="mb-3 flex items-center justify-between text-sm text-[var(--color-text-2)]">
              <span>Selected: 12 items</span>
              <Button type="link" className="px-0">
                Clear selection
              </Button>
            </div>
            <SearchActionBar
              spacing="flush"
              searchProps={{
                placeholder: 'Search paragraph',
                className: 'w-[240px]',
                allowClear: true,
                enterButton: true,
              }}
              actions={<Button danger>Batch Delete</Button>}
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SearchCombinationToolbar
            fieldConfigs={[]}
            onSearchChange={() => undefined}
            actionsClassName="flex items-center gap-2"
            actions={(
              <>
                <Segmented
                  options={[
                    { label: 'Today', value: 'today' },
                    { label: '7 Days', value: '7days' },
                  ]}
                  value="today"
                />
                <Button type="primary">Upload</Button>
              </>
            )}
          />
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SearchCombination
            fieldConfigs={[
              {
                name: 'operating_system',
                label: 'OS',
                lookup_expr: 'in',
                options: [
                  { id: 'linux', name: 'Linux' },
                  { id: 'windows', name: 'Windows' },
                  { id: 'macos', name: 'macOS' },
                ],
              },
              {
                name: 'ip',
                label: 'IP Address',
                lookup_expr: 'icontains',
              },
              {
                name: 'is_active',
                label: 'Active',
                lookup_expr: 'bool',
              },
            ]}
            fieldWidth={200}
            selectWidth={120}
            onChange={() => undefined}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Filter alignment patterns
        </div>
        <div className="grid gap-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterToolbar>
              <Input.Search allowClear className="w-48" placeholder="Operator" />
              <Select
                allowClear
                className="w-48"
                options={[
                  { label: 'System Manager', value: 'system-manager' },
                  { label: 'OpsPilot', value: 'opspilot' },
                ]}
                placeholder="Operation module"
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
            </FilterToolbar>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterToolbar className="mb-[18px]" align="start">
              <Input
                placeholder="Search source name"
                prefix={<SearchOutlined className="text-[var(--color-text-4)]" />}
                className="!w-[220px]"
                allowClear
              />
              <div className="flex items-center gap-[6px]">
                <span className="text-[13px] text-[var(--color-text-2)]">Type</span>
                <Select
                  className="!min-w-[90px]"
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'push', label: 'Push' },
                    { value: 'pull', label: 'Pull' },
                  ]}
                  value="all"
                />
              </div>
              <Button icon={<UndoOutlined />}>Reset</Button>
            </FilterToolbar>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterToolbar spacing="flush" contentClassName="gap-4" align="between">
              <div className="flex items-center gap-3">
                <span className="text-[13px] text-[var(--color-text-2)]">Level</span>
                <Select
                  className="w-[180px]"
                  options={[
                    { value: 'critical', label: 'Critical' },
                    { value: 'warning', label: 'Warning' },
                  ]}
                  value="critical"
                />
              </div>
              <div className="flex items-center gap-3">
                <TimeSelector onlyRefresh onFrequenceChange={() => undefined} onRefresh={() => undefined} />
                <Button type="primary">Apply</Button>
              </div>
            </FilterToolbar>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterToolbar spacing="default" contentClassName="gap-3" align="between">
              <Segmented
                options={[
                  { label: 'Builtin', value: 'builtin' },
                  { label: 'MCP', value: 'mcp' },
                  { label: 'Skills', value: 'skills' },
                ]}
                value="skills"
              />
              <div className="flex flex-wrap items-center gap-2">
                <Input.Search allowClear enterButton className="w-60" placeholder="Search skill package" />
                <Button>Import package</Button>
              </div>
            </FilterToolbar>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Time filter controls
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-3">
              <TimeSelector
                defaultValue={{
                  selectValue: 15,
                  rangePickerVaule: null,
                }}
                onFrequenceChange={() => undefined}
                onRefresh={() => undefined}
              />
              <TimeSelector
                defaultValue={{
                  selectValue: 15,
                  rangePickerVaule: null,
                }}
                onlyTimeSelect
              />
              <TimeSelector
                onlyRefresh
                onRefresh={() => undefined}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-3">
              <TimeSelector
                defaultValue={{
                  selectValue: 15,
                  rangePickerVaule: [dayjs().subtract(1, 'hour'), dayjs()],
                }}
                customFrequencyList={[
                  { label: '1s', value: 1 },
                  { label: '5s', value: 5 },
                  { label: '10s', value: 10 },
                ]}
                customTimeRangeList={[
                  { label: 'Last 24 hours', value: 1440 },
                  { label: 'Last 7 days', value: 10080 },
                ]}
                onFrequenceChange={() => undefined}
                onChange={() => undefined}
              />
              <TimeSelectorReadbackDemo />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Shared toolbar actions
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex items-center gap-3">
              <RefreshIconButton onClick={() => undefined} />
              <RefreshIconButton onClick={() => undefined} loading />
              <RefreshIconButton onClick={() => undefined} disabled />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex items-center gap-3">
              <RefreshIconButton onClick={() => undefined} variant="text" />
              <RefreshIconButton onClick={() => undefined} title="Refresh events" />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Tag-filter toolbars
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex items-center gap-3 overflow-x-auto">
              <SelectableTagFilterGroup
                options={[
                  { value: 'linux', label: 'Linux' },
                  { value: 'windows', label: 'Windows' },
                  { value: 'x86_64', label: 'x86_64' },
                  { value: 'arm64', label: 'ARM64' },
                ]}
                selectedValues={['linux', 'arm64']}
                onToggle={() => undefined}
                className="flex flex-wrap gap-y-2"
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex items-center gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto">
                <SelectableTagFilterGroup
                  options={[
                    { value: 'k8s', label: 'Kubernetes' },
                    { value: 'vm', label: 'Virtual machine' },
                    { value: 'redis', label: 'Redis cache' },
                  ]}
                  selectedValues={['k8s']}
                  onToggle={() => undefined}
                />
              </div>
              <Input.Search allowClear placeholder="Search nodes" className="w-60" />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Storybook structure
        </div>
        <div className="text-sm text-[var(--color-text-2)]">
          The Toolbar family is governed through split-shell, search-led, search-combination, and filter-alignment sub-contracts instead of separate leaf stories.
        </div>
      </section>
    </div>
  );
};

const TimeSelectorReadbackDemo = () => {
  const ref = useRef<TimeSelectorRef>(null);
  const [valueText, setValueText] = useState('Not read yet');

  return (
    <Space direction="vertical" size={12}>
      <TimeSelector
        ref={ref}
        defaultValue={{
          selectValue: 0,
          rangePickerVaule: [dayjs().subtract(2, 'hour'), dayjs().subtract(30, 'minute')],
        }}
      />
      <Button onClick={() => setValueText(JSON.stringify(ref.current?.getValue() ?? null))}>
        Read current value
      </Button>
      <Typography.Text type="secondary">{valueText}</Typography.Text>
    </Space>
  );
};

const meta = {
  title: 'Framework/Toolbar/FamilyOverview',
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
