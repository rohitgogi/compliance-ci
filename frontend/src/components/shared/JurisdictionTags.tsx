interface JurisdictionTagsProps {
  jurisdictions: string[];
  max?: number;
}

export default function JurisdictionTags({ jurisdictions, max = 4 }: JurisdictionTagsProps) {
  const visible = jurisdictions.slice(0, max);
  const remaining = jurisdictions.length - max;

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {visible.map((j) => (
        <span
          key={j}
          className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-accent/10 text-accent dark:text-accent-secondary"
        >
          {j}
        </span>
      ))}
      {remaining > 0 && (
        <span className="text-[10px] text-text-light-muted dark:text-text-muted">
          +{remaining}
        </span>
      )}
    </div>
  );
}
