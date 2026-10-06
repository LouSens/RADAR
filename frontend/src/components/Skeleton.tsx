/** A grey shape that stands where content is about to appear. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`skeleton block ${className}`} aria-hidden="true" />;
}

/** One card's worth of content on its way: a label, a figure, and a few lines. */
export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="glass flex flex-col gap-3 p-4 @xl:p-7" aria-hidden="true">
      <Skeleton className="h-3 w-28" />
      <Skeleton className="h-7 w-3/5" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-3 ${i === lines - 1 ? "w-2/5" : "w-full"}`} />
      ))}
    </div>
  );
}

/**
 * The shape of a page while its figures load. The page itself appears at once, so a
 * tap always goes somewhere straight away; the numbers follow.
 */
export function PageSkeleton({ cards = 2 }: { cards?: number }) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-4 @xl:gap-6">
      {Array.from({ length: cards }, (_, i) => (
        <CardSkeleton key={i} lines={i === 0 ? 4 : 3} />
      ))}
    </div>
  );
}
