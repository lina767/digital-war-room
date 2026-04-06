import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UpdatedBriefing } from "./UpdatedBriefing";
import type { ConflictData } from "@/types/conflict";

describe("UpdatedBriefing", () => {
  it("renders empty state and triggers run analysis", () => {
    const onRunAnalysis = vi.fn();
    render(
      <UpdatedBriefing
        data={null}
        conflictLabel="Iran"
        lastUpdated={null}
        onRunAnalysis={onRunAnalysis}
      />,
    );

    expect(screen.getByText(/Run analysis for Iran/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));
    expect(onRunAnalysis).toHaveBeenCalledTimes(1);
  });

  it("renders summary and things to watch when data exists", () => {
    const data = {
      conflict: "Iran",
      escalation_score: 68,
      threat_level: "HIGH",
      key_findings: ["Signal alpha"],
      scenarios: [{ description: "Status quo drift", probability: 0.4 }],
      summary: "Executive recap available.",
    } as ConflictData;

    render(
      <UpdatedBriefing
        data={data}
        conflictLabel="Iran"
        lastUpdated={new Date("2026-04-07T00:00:00Z")}
      />,
    );

    expect(screen.getByText(/Executive recap available/i)).toBeInTheDocument();
    expect(screen.getByText(/Things to Watch/i)).toBeInTheDocument();
    expect(screen.getByText(/Status quo drift/i)).toBeInTheDocument();
  });
});
