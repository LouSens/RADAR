import { Link } from "react-router-dom";

export function ComingSoon({
  title,
  phase,
  children,
}: {
  title: string;
  phase: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative flex flex-col gap-8">
      <div className="radar -right-32 -top-20 hidden w-[30rem] opacity-50 md:block" aria-hidden="true" />
      <header className="rise relative">
        <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line-strong bg-white/[0.03] px-3 py-1 text-xs text-muted">
          <span className="num text-accent">{phase}</span> Not built yet
        </p>
        <h1 className="display text-fluid-h2">{title}</h1>
      </header>
      <section className="glass rise rise-2 relative max-w-[720px] p-6">
        <h2 className="mb-3 text-lg font-semibold tracking-tight">What it will show</h2>
        <div className="space-y-3 text-muted">{children}</div>
        <Link to="/" className="btn btn-ghost mt-6">
          Back to overview
        </Link>
      </section>
    </div>
  );
}
