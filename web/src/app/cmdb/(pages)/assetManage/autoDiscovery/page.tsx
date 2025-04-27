'use client';

import { redirect } from 'next/navigation';

export default function AssetManagePage() {
  redirect('/cmdb/assetManage/autoDiscovery/collection');
  return null;
}
