type SkeletonProps = {
  className?: string;
  style?: React.CSSProperties;
  "aria-label"?: string;
};

export function Skeleton({ className = "", style, ...rest }: SkeletonProps) {
  return <div className={`skeleton ${className}`.trim()} style={style} aria-hidden={!rest["aria-label"]} {...rest} />;
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          className="skeleton-line"
          style={{ width: `${88 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

export function JobCardSkeleton() {
  return (
    <div className="job-card" aria-busy="true" aria-label="Loading job">
      <div className="job-card-header">
        <div style={{ flex: 1 }}>
          <Skeleton className="skeleton-line" style={{ width: "55%", height: 18, marginBottom: 10 }} />
          <Skeleton className="skeleton-line" style={{ width: "40%", height: 12 }} />
        </div>
        <Skeleton style={{ width: 56, height: 56, borderRadius: "50%" }} />
      </div>
      <Skeleton className="skeleton-line" style={{ width: "100%", marginTop: 16 }} />
      <Skeleton className="skeleton-line" style={{ width: "90%" }} />
      <div className="chip-row">
        <Skeleton style={{ width: 64, height: 24, borderRadius: 999 }} />
        <Skeleton style={{ width: 72, height: 24, borderRadius: 999 }} />
        <Skeleton style={{ width: 56, height: 24, borderRadius: 999 }} />
      </div>
    </div>
  );
}

export function ContactSkeleton() {
  return (
    <div className="contact-card" aria-busy="true">
      <div style={{ flex: 1 }}>
        <Skeleton className="skeleton-line" style={{ width: "45%", height: 14 }} />
        <Skeleton className="skeleton-line" style={{ width: "60%", height: 12 }} />
      </div>
      <Skeleton style={{ width: 120, height: 36, borderRadius: 8 }} />
    </div>
  );
}
