import { ItsmRuntimeSettingsProvider } from './settings/runtime-settings';

export default function ItsmLayout({ children }: { children: React.ReactNode }) {
  return <ItsmRuntimeSettingsProvider><div className="flex h-full min-h-0 flex-col">{children}</div></ItsmRuntimeSettingsProvider>;
}
