export default function ApmLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Unified APM desk canvas ≈ Storybook #fafbfc (token mix, not hardcoded hex).
  // All APM routes inherit this; route shells should stay transparent.
  return (
    <section className="h-full min-h-full bg-[color-mix(in_srgb,var(--color-bg)_65%,var(--color-background-body))]">
      {children}
    </section>
  );
}
