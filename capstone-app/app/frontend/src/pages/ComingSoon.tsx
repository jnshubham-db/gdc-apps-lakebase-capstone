import { Construction } from "lucide-react";

import { EmptyState } from "@/components/states";

export default function ComingSoon({ title, note }: { title: string; note: string }) {
  return (
    <div>
      <h1 className="mb-6 text-2xl">{title}</h1>
      <div className="bezel">
        <EmptyState title="Instrument offline" hint={note} icon={Construction} />
      </div>
    </div>
  );
}
