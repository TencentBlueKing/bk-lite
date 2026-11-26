'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="AI 设置" kind="ai" fields={['name', 'kind', 'prompt']} />;
}
