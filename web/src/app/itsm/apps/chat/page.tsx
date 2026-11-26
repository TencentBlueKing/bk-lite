'use client';

import { ResourceBoard } from '../../components/resource-board';

export default function Page() {
  return <ResourceBoard title="在线客服" kind="chats" fields={['visitor']} />;
}
