'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="交接" kind="handovers" fields={['from_user', 'to_user']} />;
}
