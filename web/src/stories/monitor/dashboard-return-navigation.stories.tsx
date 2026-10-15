import type { Meta, StoryObj } from '@storybook/nextjs';
import { useSearchParams } from '@storybook/nextjs/navigation.mock';
import { DashboardPageHeader, type DashboardPageHeaderStyles } from '@/app/monitor/dashboards/shared/widgets/dashboard-page-header';

const styles: DashboardPageHeaderStyles = {
  pageTitleRow: 'flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4',
  titleBlock: 'min-w-0',
  breadcrumb: 'mb-1 text-xs',
  title: 'm-0 text-base font-semibold text-[var(--color-text-1)]',
  controlsWrap: 'flex flex-wrap items-center gap-2',
  modePills: 'inline-flex items-center gap-1.5',
  modePill: 'h-7 rounded-full border border-[#1677ff] bg-white px-3 text-[13px] font-medium text-[#1677ff]',
  modePillActive: '!bg-[#1677ff] !text-white',
  toolbarBackBtn: '',
  actionButtons: 'flex items-center'
};

interface DashboardReturnNavigationPreviewProps {
  source: 'view' | 'integration';
  objectName: string;
}

const DashboardReturnNavigationPreview = ({ source, objectName }: DashboardReturnNavigationPreviewProps) => {
  const params = new URLSearchParams({
    return_object_id: '16',
    return_object_name: objectName,
    ...(source === 'integration' ? { return_source: 'integration' } : {})
  });
  useSearchParams.mockImplementation(() => params as ReturnType<typeof useSearchParams>);

  return <div className="max-w-[560px]">
    <DashboardPageHeader
      title={`${objectName}监控仪表盘`}
      displayMode="dashboard"
      onDisplayModeChange={() => undefined}
      timeDefaultValue={{ selectValue: 15, rangePickerVaule: null }}
      onTimeChange={() => undefined}
      onFrequenceChange={() => undefined}
      onRefresh={() => undefined}
      styles={styles}
    />
  </div>;
};

const meta: Meta<typeof DashboardReturnNavigationPreview> = {
  title: 'Monitor/Dashboard/Return Navigation',
  component: DashboardReturnNavigationPreview,
  parameters: { layout: 'padded' }
};

export default meta;
type Story = StoryObj<typeof DashboardReturnNavigationPreview>;

export const FromView: Story = {
  args: { source: 'view', objectName: 'MongoDB' }
};

export const FromIntegrationAsset: Story = {
  args: { source: 'integration', objectName: 'MongoDB' }
};

export const LongObjectNameInNarrowContainer: Story = {
  args: { source: 'integration', objectName: '生产环境华南区域核心交易数据库集群' }
};
