'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="业务对象" kind="biz_objects" fields={['name', 'key']} />;
}
