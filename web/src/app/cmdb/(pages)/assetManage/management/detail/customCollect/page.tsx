'use client';

import PluginManager from '@/app/cmdb/(pages)/assetManage/autoDiscovery/customPlugin/PluginManager';
import { useModelDetail } from '../context';

export default function ModelCustomCollectPage() {
  const modelDetail = useModelDetail();
  return <PluginManager lockedModelId={modelDetail?.model_id || ''} />;
}
