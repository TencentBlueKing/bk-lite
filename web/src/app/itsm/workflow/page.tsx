'use client';

import { ConditionBuilder } from '../components/condition-builder';
import { FlowDesigner } from '../components/flow-designer';

export default function WorkflowPage() {
  return (
    <div>
      <FlowDesigner />
      <ConditionBuilder fields={['form.amount', 'form.priority']} onChange={() => undefined} />
    </div>
  );
}
