export default function ApmLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <section className="min-h-full bg-[var(--color-bg-1)]">{children}</section>;
}
