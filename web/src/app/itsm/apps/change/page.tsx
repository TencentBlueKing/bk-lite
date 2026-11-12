'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="变更窗口" kind="changes" fields={['name']} />;
}
