import { useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/lib/utils";

export type AsyncTokenStatus = "loading" | "success" | "error";

/**
 * Runs an async action once when `token` is non-empty; stable `run` via ref (no useCallback needed at call site).
 */
export function useAsyncTokenResult(
  token: string,
  emptyTokenMessage: string,
  run: (t: string) => Promise<{ message: string }>,
): { status: AsyncTokenStatus; message: string } {
  const [status, setStatus] = useState<AsyncTokenStatus>("loading");
  const [message, setMessage] = useState("");
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage(emptyTokenMessage);
      return;
    }
    let cancelled = false;
    setStatus("loading");
    setMessage("");
    runRef
      .current(token)
      .then((res) => {
        if (!cancelled) {
          setStatus("success");
          setMessage(res.message);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setStatus("error");
          setMessage(getErrorMessage(err, "Request failed."));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, emptyTokenMessage]);

  return { status, message };
}
