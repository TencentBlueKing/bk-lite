'use client';
import { redirect } from 'next/navigation';
import { useSearchParams } from 'next/navigation';

export default function AssetDetail() {
  const searchParams = useSearchParams();
  const objIcon = searchParams.get('icn');
  const modelName = searchParams.get('model_name');
  const modelId = searchParams.get('model_id');
  const classificationId = searchParams.get('classification_id');
  const instId = searchParams.get('inst_id');
  const instName = searchParams.get('inst_name');
  redirect(
    `/cmdb/assetData/detail/baseInfo?icn=${objIcon}&model_name=${modelName}&model_id=${modelId}&classification_id=${classificationId}&inst_id=${instId}&inst_name=${instName}`
  );
  return null;
}
