'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="满意度模板" kind="surveys" fields={['name']} />;
}
