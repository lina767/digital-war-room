import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConflictData } from "@/types/conflict";
import { LatestHeadlines } from "./LatestHeadlines";

describe("LatestHeadlines", () => {
  const sampleData = {
    news: {
      articles: [
        { title: "Story A", source: "Reuters", url: "https://example.com/a" },
        { title: "Story B", source: "BBC", url: "https://example.com/b" },
      ],
    },
  } as ConflictData;

  it("renders incoming headlines", () => {
    render(<LatestHeadlines data={sampleData} />);

    expect(screen.getByText("Story A")).toBeInTheDocument();
    expect(screen.getByText("Story B")).toBeInTheDocument();
    expect(screen.getByText(/2 stories/i)).toBeInTheDocument();
  });

  it("calls source filter change handlers", () => {
    const onAllowedSourceKeysChange = vi.fn();
    render(
      <LatestHeadlines
        data={sampleData}
        allowedSourceKeys={new Set()}
        onAllowedSourceKeysChange={onAllowedSourceKeysChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Filter headlines to major wire services/i }));
    expect(onAllowedSourceKeysChange).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Toggle headline source Reuters/i }));
    expect(onAllowedSourceKeysChange).toHaveBeenCalledTimes(2);
  });
});
