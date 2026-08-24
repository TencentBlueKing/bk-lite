export default function ApmLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <section className="h-full min-h-full">
      {children}
    </section>
  );
}
