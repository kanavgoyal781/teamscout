import { Inbox } from "lucide-react";

type EmptyStateProps = {
  title?: string;
  instruction: string;
  icon?: React.ReactNode;
};

export default function EmptyState({ title, instruction, icon }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      {icon ?? <Inbox size={28} strokeWidth={1.5} aria-hidden />}
      {title ? <p style={{ fontWeight: 600, color: "var(--text-secondary)", margin: "8px 0 0" }}>{title}</p> : null}
      <p>{instruction}</p>
    </div>
  );
}
