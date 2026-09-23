import { redirect } from 'next/navigation';

export default async function LegacyApplicationSetupPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  redirect(`/rum/setup/${encodeURIComponent(name)}`);
}
