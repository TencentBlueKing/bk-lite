'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="打印模板" kind="prints" fields={['name', 'body']} />;
}
