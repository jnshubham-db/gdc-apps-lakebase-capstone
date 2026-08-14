import * as Tabs from "@radix-ui/react-tabs";

export function ToneNav({ tabs }: { tabs: { value: string; label: string }[] }) {
  return (
    <Tabs.List className="flex flex-wrap gap-1 border-b border-bezel">
      {tabs.map((t) => (
        <Tabs.Trigger
          key={t.value}
          value={t.value}
          className="relative -mb-px border-b-2 border-transparent px-4 py-2.5 font-display text-sm uppercase tracking-[0.14em] text-muted transition-colors hover:text-lum focus:outline-none data-[state=active]:border-green data-[state=active]:text-green data-[state=active]:text-glow-green"
        >
          {t.label}
        </Tabs.Trigger>
      ))}
    </Tabs.List>
  );
}
