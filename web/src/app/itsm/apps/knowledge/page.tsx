'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="知识" kind="knowledge" fields={['title', 'content']} />;
}
