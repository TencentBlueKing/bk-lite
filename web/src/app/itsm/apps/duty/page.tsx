'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="值班" kind="duties" fields={['name']} />;
}
