import { useEffect, useState } from "react";

/** Matches Tailwind `lg` breakpoint (1024px). */
export const LG_MIN_WIDTH = 1024;

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** True below the `lg` breakpoint – mobile / tablet portrait layouts. */
export function useIsMobileLayout(): boolean {
  return useMediaQuery(`(max-width: ${LG_MIN_WIDTH - 1}px)`);
}
