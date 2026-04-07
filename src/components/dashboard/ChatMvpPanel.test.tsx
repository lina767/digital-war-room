import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMvpPanel } from "./ChatMvpPanel";

const mockAsk = vi.fn();
const mockFeedback = vi.fn();

vi.mock("@/lib/api/chat", () => ({
  postChatAsk: (...args: unknown[]) => mockAsk(...args),
  postChatFeedback: (...args: unknown[]) => mockFeedback(...args),
}));

describe("ChatMvpPanel", () => {
  it("renders confidence and sources from ask response", async () => {
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
  });
});
