import { TicketWorkbench } from '../components/ticket-workbench';

export default async function TicketsPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  const initialTab = ['all', 'mine', 'created', 'following', 'history'].includes(tab || '') ? tab : 'all';
  return <TicketWorkbench key={initialTab} initialTab={initialTab} />;
}
