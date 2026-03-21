import { cn } from "@/lib/utils";

/**
 * Renders cross-stream narrative text with paragraph breaks when the backend uses blank lines.
 * Improves reading flow vs. a single dense block.
 */
export function NarrativeBody({
  text,
  className,
  paragraphClassName,
}: {
  text: string;
  className?: string;
  paragraphClassName?: string;
}) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const parts = trimmed.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  if (parts.length <= 1) {
    return (
      <p
        className={cn(
          "text-sm leading-[1.65] text-pretty text-foreground/95 whitespace-pre-wrap",
          paragraphClassName,
          className,
        )}
      >
        {trimmed}
      </p>
    );
  }
  return (
    <div className={cn("space-y-4", className)}>
      {parts.map((p, i) => (
        <p
          key={i}
          className={cn(
            "text-sm leading-[1.65] text-pretty text-foreground/95 whitespace-pre-wrap",
            paragraphClassName,
          )}
        >
          {p}
        </p>
      ))}
    </div>
  );
}
