'use client';

import { useState } from 'react';
import { Alert, Radio, Select } from 'antd';
import { ItsmModal } from './interaction-surfaces';
import { useTicketFormFields } from './ticket-form-filters';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketCenterFilters } from '../types';

export function TicketExportDialog({ filters, selected, total, onClose, onSubmitted }: {
  filters: TicketCenterFilters;
  selected: number[];
  total: number;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const { exportTickets } = useItsmApi();
  const [scope, setScope] = useState(selected.length ? 'selected' : 'filtered');
  const [formColumns, setFormColumns] = useState<string[]>([]);
  const { fields, loading, error } = useTicketFormFields(filters.workflow_id, true);
  const count = scope === 'selected' ? selected.length : total;
  const submitExport = async () => {
    await exportTickets(filters, formColumns, scope === 'selected' ? selected : undefined);
    onSubmitted();
  };

  return <ItsmModal open title="导出工单" okText="提交导出" onOk={submitExport} onCancel={onClose}
    okButtonProps={{ disabled: !count || count > 5000 }}>
    <div className="flex flex-col gap-4">
      <Radio.Group value={scope} onChange={event => setScope(event.target.value)}
        options={[
          { value: 'filtered', label: `当前筛选结果（${total}）` },
          { value: 'selected', label: `已选工单（${selected.length}）`, disabled: !selected.length },
        ]} />
      {count > 5000 && <Alert type="warning" showIcon message="一次最多导出 5000 张工单，请缩小筛选范围或勾选要导出的工单。" />}
      <p className="m-0 text-sm text-[var(--color-text-2)]">包含单号、标题、提单人和状态。文件生成后可在导出记录下载。</p>
      {filters.workflow_id && <label className="flex flex-col gap-1">表单字段
        <Select aria-label="导出表单字段" mode="multiple" allowClear showSearch optionFilterProp="label" maxCount={30}
          loading={loading} value={formColumns} options={fields.map(field => ({ value: field.key, label: field.label }))}
          placeholder="选择要附加的表单字段" onChange={setFormColumns} />
      </label>}
      {error && <Alert type="warning" showIcon message={error} />}
      {!filters.workflow_id && <span className="text-xs text-[var(--color-text-3)]">按流程筛选后，可附加该流程的表单字段。</span>}
    </div>
  </ItsmModal>;
}
