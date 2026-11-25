import { redirect } from 'next/navigation';

export default function SyslogSourceDeviceRedirectPage() {
  redirect('/log/integration/receive?collect_type=syslog');
}
