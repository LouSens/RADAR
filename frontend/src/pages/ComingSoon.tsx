import { Panel } from "../components/ui";

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
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-muted">Not built yet. This screen arrives in {phase}.</p>
      </header>
      <Panel title="What it will show">
        <div className="max-w-[68ch] space-y-2 text-sm">{children}</div>
      </Panel>
    </div>
  );
}
