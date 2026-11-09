'use client';

import { FormDesigner } from '../components/form-designer';
import { FormRenderer } from '../components/form-renderer';

const schema = { version: 1, fields: [{ key: 'title', type: 'input', label: '标题', required: true }] };

export default function FormPage() {
  return (
    <div className="grid grid-cols-2 gap-4">
      <FormDesigner />
      <FormRenderer schema={schema} onSubmit={() => undefined} />
    </div>
  );
}
