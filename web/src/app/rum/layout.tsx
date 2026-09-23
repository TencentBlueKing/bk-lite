export default function RumLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {children}
    </section>
  );
}
