import { useEffect, useRef } from "react";

const tickerItems = [
  "● RC-135 Rivet Joint detected over Persian Gulf — 3rd pass in 6 hours",
  "● Brent crude +4.2% — highest single-day move in 3 weeks",
  "● Polymarket: US-Iran conflict 34%",
  "● IRGC mobilization reports on 3 Telegram channels",
  "● NetBlocks: Iran internet connectivity degraded 12%",
  "● IDF reserves called up — Channel 12 reports",
  "● USS Eisenhower carrier strike group enters Strait of Hormuz",
  "● NOTAM issued for Tehran FIR — airspace restrictions expanding",
];

export function LiveTicker() {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
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
  }, []);

  const content = tickerItems.join("     ");

  return (
    <div className="w-full bg-card border-b border-border overflow-hidden h-7 flex items-center flex-shrink-0">
      <div ref={scrollRef} className="whitespace-nowrap font-mono text-[11px] text-primary">
        <span>{content}</span>
        <span className="ml-16">{content}</span>
      </div>
    </div>
  );
}
