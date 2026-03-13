import { useEffect, useState, useCallback } from "react";
import {
  fetchGreynoiseThreats,
  fetchGreynoiseTrend,
  type GreynoiseResult,
  type GreynoiseTrendPoint,
} from "@/lib/api";

interface UseGreynoiseThreatsReturn {
  data: GreynoiseResult | null;
  trendData: GreynoiseTrendPoint[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useGreynoiseThreats(conflict: string): UseGreynoiseThreatsReturn {
  const [data, setData] = useState<GreynoiseResult | null>(null);
  const [trendData, setTrendData] = useState<GreynoiseTrendPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!conflict) return;
    setIsLoading(true);
    setError(null);

    Promise.all([fetchGreynoiseThreats(conflict), fetchGreynoiseTrend(conflict, 7)])
      .then(([snapshot, trend]) => {
        if (snapshot) {
          setData(snapshot);
          setError(null);
        } else {
          setError("No GreyNoise data available yet.");
        }
        if (trend?.trend) {
          setTrendData(trend.trend);
        }
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [conflict]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 120_000);
    return () => clearInterval(interval);
  }, [load]);

  return { data, trendData, isLoading, error, refresh: load };
}
