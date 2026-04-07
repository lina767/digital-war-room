import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMvpPanel } from "./ChatMvpPanel";

const mockAsk = vi.fn();
const mockFeedback = vi.fn();
const mockGetAnalyzeStatus = vi.fn();
const mockTriggerRefresh = vi.fn();

vi.mock("@/lib/api/chat", () => ({
  postChatAsk: (...args: unknown[]) => mockAsk(...args),
  postChatFeedback: (...args: unknown[]) => mockFeedback(...args),
}));

vi.mock("@/lib/api/analyze", () => ({
  getAnalyzeStatus: (...args: unknown[]) => mockGetAnalyzeStatus(...args),
  triggerRefreshAnalysis: (...args: unknown[]) => mockTriggerRefresh(...args),
}));

describe("ChatMvpPanel", () => {
  beforeEach(() => {
    mockAsk.mockReset();
    mockFeedback.mockReset();
    mockGetAnalyzeStatus.mockReset();
    mockTriggerRefresh.mockReset();
    mockTriggerRefresh.mockResolvedValue({ status: "started", conflict: "Iran" });
  });

  it("sends on Enter but not on Shift+Enter", async () => {
    mockGetAnalyzeStatus.mockResolvedValueOnce({ cached: true });
    mockAsk.mockResolvedValueOnce({
      response_id: "cc5f8689-b7fb-4489-bfe2-c047c9352436",
      question_type: "risk_assessment",
      answer: "Risk is currently elevated due to activity concentration.",
      confidence_score: 0.78,
      sources: ["https://example.com/a"],
      fallback_used: false,
    });

    render(<ChatMvpPanel conflict="Iran" />);
    const input = screen.getByPlaceholderText(/Ask about current situation/i);
    fireEvent.change(input, { target: { value: "What are the current risks?" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(mockAsk).toHaveBeenCalledTimes(0);

    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(mockAsk).toHaveBeenCalledTimes(1));
  });

  it("renders confidence and sources from ask response", async () => {
    mockGetAnalyzeStatus.mockResolvedValueOnce({ cached: true });
    mockAsk.mockResolvedValueOnce({
      response_id: "cc5f8689-b7fb-4489-bfe2-c047c9352436",
      question_type: "risk_assessment",
      answer: "Risk is currently elevated due to activity concentration.",
      confidence_score: 0.78,
      sources: ["https://example.com/a"],
      fallback_used: false,
    });

    render(<ChatMvpPanel conflict="Iran" />);
    fireEvent.change(screen.getByPlaceholderText(/Ask about current situation/i), {
      target: { value: "What are the current risks?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() =>
      expect(screen.getByText(/Risk is currently elevated/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Confidence: 78%/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://example.com/a" })).toBeInTheDocument();
  });

  it("sends helpful feedback for a response", async () => {
    mockGetAnalyzeStatus.mockResolvedValueOnce({ cached: true });
    mockAsk.mockResolvedValueOnce({
      response_id: "1e2904d5-8401-4658-aa6d-24539e832c6d",
      question_type: "changes_since_yesterday",
      answer: "No major force posture changes are confirmed.",
      confidence_score: 0.66,
      sources: [],
      fallback_used: false,
    });
    mockFeedback.mockResolvedValueOnce(undefined);

    render(<ChatMvpPanel conflict="Iran" />);
    fireEvent.change(screen.getByPlaceholderText(/Ask about current situation/i), {
      target: { value: "What changed since yesterday?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() =>
      expect(screen.getByText(/No major force posture changes/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(mockFeedback).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Helpful" })).toBeDisabled();
  });

  it("keeps a short chat history of previous turns", async () => {
    mockGetAnalyzeStatus.mockResolvedValue({ cached: true });
    mockAsk
      .mockResolvedValueOnce({
        response_id: "one",
        question_type: "situation_overview",
        answer: "First answer.",
        confidence_score: 0.7,
        sources: [],
        fallback_used: false,
      })
      .mockResolvedValueOnce({
        response_id: "two",
        question_type: "risk_assessment",
        answer: "Second answer.",
        confidence_score: 0.6,
        sources: [],
        fallback_used: false,
      });

    render(<ChatMvpPanel conflict="Iran" />);
    const input = screen.getByPlaceholderText(/Ask about current situation/i);

    fireEvent.change(input, { target: { value: "First question?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText("First answer.")).toBeInTheDocument());

    fireEvent.change(input, { target: { value: "Second question?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText("Second answer.")).toBeInTheDocument());

    expect(screen.getByText("First answer.")).toBeInTheDocument();
  });

  it("renders request errors inside the related turn", async () => {
    mockGetAnalyzeStatus.mockResolvedValueOnce({ cached: true });
    mockAsk.mockRejectedValueOnce(new Error("Chat failed hard"));

    render(<ChatMvpPanel conflict="Iran" />);
    fireEvent.change(screen.getByPlaceholderText(/Ask about current situation/i), {
      target: { value: "Will this fail?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByText("Chat failed hard")).toBeInTheDocument());
  });
});
