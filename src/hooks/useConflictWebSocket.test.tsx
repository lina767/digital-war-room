import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConflictWebSocket } from "./useConflictWebSocket";

const apiMock = vi.hoisted(() => ({
  getApiBase: vi.fn(() => "http://localhost:8000"),
  getWsUrl: vi.fn((path: string) => `ws://localhost:8000${path}`),
  getLatestAnalysis: vi.fn(),
  getAnalyzeStatus: vi.fn(),
  triggerRefreshAnalysis: vi.fn(),
  normalizeAnalysisResponse: vi.fn((x) => x),
}));

vi.mock("@/lib/api", () => apiMock);
vi.mock("sonner", () => ({ toast: { info: vi.fn() } }));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  emitOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

describe("useConflictWebSocket", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);

    apiMock.getLatestAnalysis.mockResolvedValue({ data: null, fromCache: false });
    apiMock.getAnalyzeStatus.mockResolvedValue({ cached: false });
    apiMock.triggerRefreshAnalysis.mockResolvedValue({ status: "started", conflict: "Iran" });
  });

  it("loads cached analysis on mount", async () => {
    const cached = { conflict: "Iran", escalation_score: 55, key_findings: [], scenarios: [], summary: null };
    apiMock.getLatestAnalysis.mockResolvedValueOnce({ data: cached, fromCache: true });

    const { result } = renderHook(() => useConflictWebSocket({ conflict: "Iran", enabled: true }));

    expect(MockWebSocket.instances.length).toBe(1);
    act(() => {
      MockWebSocket.instances[0]?.emitOpen();
    });

    await waitFor(() => {
      expect(result.current.data?.conflict).toBe("Iran");
      expect(result.current.dataFromCache).toBe(true);
      expect(result.current.initialLoadPending).toBe(false);
    });
  });

  it("updates state from websocket ok message", async () => {
    const { result } = renderHook(() => useConflictWebSocket({ conflict: "Iran", enabled: true }));

    act(() => {
      MockWebSocket.instances[0]?.emitOpen();
      MockWebSocket.instances[0]?.emitMessage({
        status: "ok",
        conflict: "Iran",
        escalation_score: 72,
        key_findings: [],
        scenarios: [],
        summary: "snapshot",
      });
    });

    await waitFor(() => {
      expect(result.current.status).toBe("connected");
      expect(result.current.data?.escalation_score).toBe(72);
      expect(result.current.analysisError).toBeNull();
    });
  });

  it("sets backend-unreachable error when status endpoint returns null", async () => {
    apiMock.getLatestAnalysis.mockResolvedValue({ data: null, fromCache: false });
    apiMock.getAnalyzeStatus.mockResolvedValueOnce(null);

    const { result } = renderHook(() => useConflictWebSocket({ conflict: "Iran", enabled: true }));

    await waitFor(() => {
      expect(result.current.analysisError).toContain("Backend unreachable");
      expect(result.current.initialLoadPending).toBe(false);
    });
  });
});
