import TicketDetailPage from '../../components/ticket-detail-page';

export default async function Page({ searchParams }: { searchParams: Promise<{ from?: string }> }) {
  const { from } = await searchParams;
  return <TicketDetailPage fromTicketCenter={from === 'tickets'} />;
}
