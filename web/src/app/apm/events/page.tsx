import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ApmEventsLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/events/alerts', await searchParams);
}
