import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const indexPayload = {
  generated: "test-generation",
  runs: [{
    id: "duel-test",
    type: "duel",
    source: "committed",
    verdict: "PLN wins all 1 mirror game(s)",
    has_moves: false,
    games: [{
      subdir: "g1",
      winner: "pln",
      moves_logged: false,
      stats: {
        pln: { final: { n_cities: 2, n_units: 4, n_techs: 1 }, avg_proposed: 3, avg_conclusions: 2, pct_actions_eq_recs: 50 },
        plain: { final: { n_cities: 1, n_units: 2, n_techs: 0 }, avg_proposed: 2 },
      },
    }],
  }],
  fixtures: { sample: { ok: true } },
};
const atomPayload = { facts: [{ category: "units", statement: "(Inheritance Unit_1 Type_settlers)", stv: "(stv 1 0.99)" }], rules: [], recommendations: [] };

describe("FreeCiv observatory adapter", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(url.includes("atoms") ? atomPayload : indexPayload),
    })));
  });

  it("renders the imported Decision Observatory shell with benchmark data", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("OmegaClaw Decision Observatory")).toBeInTheDocument());
    expect(screen.getAllByText("duel-test").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PLN wins all 1 mirror game(s)").length).toBeGreaterThan(0);
    expect(screen.getByText("OmegaClaw+PLN vs plain LLM")).toBeInTheDocument();
  });
});
