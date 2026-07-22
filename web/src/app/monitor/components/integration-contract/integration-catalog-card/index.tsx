import React from 'react';

interface IntegrationCatalogCardProps {
  media: React.ReactNode;
  title: React.ReactNode;
  details?: React.ReactNode;
  description: React.ReactNode;
  menu?: React.ReactNode;
  action: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

const IntegrationCatalogCard: React.FC<IntegrationCatalogCardProps> = ({
  media,
  title,
  details,
  description,
  menu,
  action,
  onClick,
  className = '',
}) => {
  return (
    <div
      className={`bg-[var(--color-bg-1)] relative rounded-lg border p-4 shadow-sm transition-shadow duration-300 ease-in-out hover:shadow-md ${className}`}
      onClick={onClick}
    >
      {menu ? (
        <div className="absolute right-[12px] top-[12px]" onClick={(event) => event.stopPropagation()}>
          {menu}
        </div>
      ) : null}
      <div className="my-2 flex items-center space-x-4">
        {media}
        <div className="min-w-0 flex-1">
          <h2 className="m-0 hide-text text-xl font-bold" title={typeof title === 'string' ? title : undefined}>
            {title}
          </h2>
          {details ? <div className="mt-[4px] flex flex-wrap items-center gap-[6px]">{details}</div> : null}
        </div>
      </div>
      <p
        className="mb-[15px] h-[54px] overflow-hidden text-[13px] text-[var(--color-text-3)] line-clamp-3"
        title={typeof description === 'string' ? description : undefined}
      >
        {description}
      </p>
      <div className="flex h-[32px] w-full items-end justify-center">{action}</div>
    </div>
  );
};

export default IntegrationCatalogCard;
