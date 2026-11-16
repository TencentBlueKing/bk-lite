import TicketDetailPage from '../../components/ticket-detail-page';
import { redirect } from 'next/navigation';

export default async function Page({ searchParams }: { searchParams: Promise<{ service_id?: string }> }) {
  const { service_id } = await searchParams;
  const serviceId = Number(service_id);
  if (!Number.isSafeInteger(serviceId) || serviceId < 1) redirect('/itsm/portal');
  return <TicketDetailPage key={serviceId} serviceId={serviceId} />;
}
