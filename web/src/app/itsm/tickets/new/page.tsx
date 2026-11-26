import TicketDetailPage from '../../components/ticket-detail-page';
import { redirect } from 'next/navigation';

export default async function Page({ searchParams }: { searchParams: Promise<{ service_id?: string; from?: string }> }) {
  const { service_id, from } = await searchParams;
  const serviceId = Number(service_id);
  if (!Number.isSafeInteger(serviceId) || serviceId < 1) redirect('/itsm/portal');
  return <TicketDetailPage key={serviceId} serviceId={serviceId} fromTicketCenter={from === 'tickets'} />;
}
