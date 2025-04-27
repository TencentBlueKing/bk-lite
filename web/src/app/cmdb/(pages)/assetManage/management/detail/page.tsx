'use client';
import { redirect } from 'next/navigation';
import { useSearchParams } from 'next/navigation';

export default function AssetDetail() {
  const searchParams = useSearchParams().toString();
  redirect(`/cmdb/assetManage/management/detail/attributes?${searchParams}`);
  return null;
}
