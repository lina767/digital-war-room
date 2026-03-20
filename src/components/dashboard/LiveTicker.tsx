import { useEffect, useRef, useState } from "react";
import type { ConflictData } from "@/hooks/useConflictWebSocket";

const FALLBACK_ITEMS = [
  "● RC-135 Rivet Joint detected over Persian Gulf — 3rd pass in 6 hours",
  "● Brent crude +4.2% — highest single-day move in 3 weeks",
  "● Polymarket: Iran conflict 34%",
  "● IRGC mobilization reports on 3 Telegram channels",
  "● NetBlocks: Iran internet connectivity degraded 12%",
  "● IDF reserves called up — Channel 12 reports",
  "● USS Eisenhower carrier strike group enters Strait of Hormuz",
  "● NOTAM issued for Tehran FIR — airspace restrictions expanding",
];

interface LiveTickerProps {
  /** When provided, headlines from latest analysis are shown in the ticker */
  conflictData?: ConflictData | null;
}

export function LiveTicker({ conflictData }: LiveTickerProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  const fromData = (conflictData?.news?.articles ?? [])
    .slice(0, 12)
    .map((a) => `● ${a.title || ""}`)
    .filter(Boolean);
  const tickerItems = fromData.length > 0 ? (fromData as string[]) : FALLBACK_ITEMS;
  const articleCount = conflictData?.news?.articles?.length ?? 0;

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mq.matches);
    const handler = () => setPrefersReducedMotion(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const el = scrollRef.current;
    if (!el) return;
    let animId: number;
    let pos = 0;
    const speed = 0.5;

    const animate = () => {
      pos -= speed;
      if (Math.abs(pos) >= el.scrollWidth / 2) pos = 0;
      el.style.transform = `translateX(${pos}px)`;
      animId = requestAnimationFrame(animate);
    };
    animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [articleCount, prefersReducedMotion]);

  const content = tickerItems.join("     ");

  return (
    <div className="w-full bg-card border-b border-border overflow-hidden h-8 sm:h-7 flex items-center flex-shrink-0">
      <div ref={scrollRef} className="whitespace-nowrap font-mono text-xs sm:text-[11px] text-primary">
        <span>{content}</span>
        <span className="ml-16">{content}</span>
      </div>
    </div>
  );
}
