import { redirect } from 'next/navigation';

export default function ApmDeploymentsRedirectPage() {
  redirect('/apm/services');
}
