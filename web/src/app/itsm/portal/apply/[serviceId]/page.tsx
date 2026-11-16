import { redirect } from 'next/navigation';

export default async function Page({ params }: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await params;
  const id = Number(serviceId);
  if (!Number.isSafeInteger(id) || id < 1) redirect('/itsm/portal');
  redirect(`/itsm/tickets/new?service_id=${id}`);
}
