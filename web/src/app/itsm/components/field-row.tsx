export function FieldRow({
  label,
  children,
  align = 'center',
}: {
  label: string;
  children: React.ReactNode;
  align?: 'center' | 'start';
}) {
  return (
    <div className={`flex gap-3 text-sm ${align === 'start' ? 'items-start' : 'items-center'}`}>
      <span className={`w-[7.5rem] shrink-0 text-right leading-5 text-[var(--color-text-2)] ${align === 'start' ? 'pt-1.5' : ''}`}>{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
