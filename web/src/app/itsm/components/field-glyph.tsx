export const FIELD_GROUP_COLOR = {
  basic: 'var(--color-text-2)',
  senior: 'var(--color-warning)',
  scene: 'var(--color-success)',
} as const;

export function FieldGlyph({ type }: { type: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
      {paths(type)}
    </svg>
  );
}

function paths(type: string) {
  if (type === 'textarea') {
    return (
      <>
        <path d="M2.5 3.5h11M2.5 6.5h11M2.5 9.5h11M2.5 12.5h7" />
      </>
    );
  }
  if (type === 'number' || type === 'calculate') {
    return (
      <>
        <path d="M5 2.5v11M11 2.5v11M2.5 5.5h11M2.5 10.5h11" />
      </>
    );
  }
  if (type === 'radio') {
    return (
      <>
        <circle cx="8" cy="8" r="5.2" />
        <circle cx="8" cy="8" r="2" fill="currentColor" stroke="none" />
      </>
    );
  }
  if (type === 'checkbox') {
    return (
      <>
        <rect x="2.5" y="2.5" width="11" height="11" rx="2" />
        <path d="M4.5 8.2l2.2 2.2 4.6-4.8" />
      </>
    );
  }
  if (type === 'select' || type === 'cmdb' || type === 'singleAssociateConfig') {
    return (
      <>
        <rect x="2" y="3" width="12" height="10" rx="2" />
        <path d="M6 7.2l2 2 2-2" />
      </>
    );
  }
  if (type === 'multiselect' || type === 'multiCmdb' || type === 'associateConfig') {
    return (
      <>
        <rect x="2" y="2.5" width="9" height="7" rx="1.5" />
        <path d="M5 12.5h9v-7" />
      </>
    );
  }
  if (type === 'cascade' || type === 'multiCascade') {
    return (
      <>
        <path d="M3 3.5h4M3 8h4M3 12.5h4" />
        <path d="M8 3.5l2 2-2 2M8 8l2 2" />
      </>
    );
  }
  if (type === 'date' || type === 'datetime' || type === 'dateRange') {
    return (
      <>
        <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
        <path d="M2.5 7h11M5.5 2.5v2M10.5 2.5v2" />
      </>
    );
  }
  if (type === 'time') {
    return (
      <>
        <circle cx="8" cy="8" r="5.2" />
        <path d="M8 5v3.2l2.2 1.4" />
      </>
    );
  }
  if (type === 'richtext') {
    return (
      <>
        <path d="M3 13l2.2-7h1.2L8.5 13M4 10.5h3.4" />
        <path d="M10 5.5h3.5M11.7 5.5V13" />
      </>
    );
  }
  if (type === 'user' || type === 'organization') {
    return (
      <>
        <circle cx="8" cy="5.2" r="2.2" />
        <path d="M3.5 13.2c.6-2.3 2.3-3.4 4.5-3.4s3.9 1.1 4.5 3.4" />
      </>
    );
  }
  if (type === 'multiUser' || type === 'userGroup' || type === 'multiUserGroup') {
    return (
      <>
        <circle cx="6" cy="5.5" r="2" />
        <circle cx="10.5" cy="6" r="1.6" />
        <path d="M2.5 13c.5-2 1.9-3 3.5-3s3 1 3.5 3M10 10.2c1.2.1 2.2.8 2.6 2.3" />
      </>
    );
  }
  if (type === 'section') {
    return (
      <>
        <rect x="2" y="3" width="12" height="10" rx="1.5" />
        <path d="M2 6.5h12" />
      </>
    );
  }
  if (type === 'table' || type === 'nestedTable' || type === 'task' || type === 'cab') {
    return (
      <>
        <rect x="2" y="3" width="12" height="10" rx="1.5" />
        <path d="M2 6.5h12M2 10h12M6.5 6.5V13M10 6.5V13" />
      </>
    );
  }
  if (type === 'tab') {
    return (
      <>
        <path d="M2.5 6.5V13h11V6.5" />
        <path d="M2.5 6.5h3.2l.8-2h3l.8 2H13.5" />
      </>
    );
  }
  if (type === 'attachment') {
    return <path d="M10.5 3.5l-5 5a2.2 2.2 0 103.1 3.1l5.2-5.2a3.3 3.3 0 10-4.6-4.6L4 7" />;
  }
  if (type === 'link') {
    return (
      <>
        <path d="M6.8 9.2l2.4-2.4" />
        <path d="M7.2 5.2l1.2-1.2a2.4 2.4 0 013.4 3.4L10.6 8.6" />
        <path d="M8.8 10.8l-1.2 1.2a2.4 2.4 0 01-3.4-3.4L5.4 7.4" />
      </>
    );
  }
  if (type === 'subProcessForm') {
    return (
      <>
        <rect x="2" y="2.5" width="5" height="4" rx="1" />
        <rect x="9" y="9.5" width="5" height="4" rx="1" />
        <path d="M4.5 6.5v2.2h6V9.5" />
      </>
    );
  }
  if (type === 'signature') {
    return <path d="M2.5 11.5c2-3 2.4-5.5 3.2-5.5.9 0 .6 4 1.8 4s1.2-6 2.2-6 1 4.2 2 4.2.6-1.5 1.8-1.5" />;
  }
  return (
    <>
      <path d="M3 4.5h10M3 8h10M3 11.5h6" />
    </>
  );
}
