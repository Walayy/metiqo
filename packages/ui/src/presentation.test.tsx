import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Metric, MetricGrid } from "./presentation";

describe("Metric", () => {
  it("keeps named financial regions and valid term/definition associations", () => {
    render(
      <MetricGrid>
        <Metric
          aria-label="ROI / yield"
          detail="Sur 24 paris réglés"
          emphasis="statistic"
          label="ROI / yield"
          role="region"
          value="8,5 %"
        />
        <Metric label="Mises totales" value="1 000 €" />
      </MetricGrid>,
    );

    const region = screen.getByRole("region", { name: "ROI / yield" });
    const term = within(region).getByRole("term");
    const definitions = within(region).getAllByRole("definition");
    expect(term).toHaveTextContent("ROI / yield");
    expect(definitions.map((item) => item.textContent)).toEqual(["8,5 %", "Sur 24 paris réglés"]);
    expect(term.closest("dl")).not.toBeNull();
    expect(definitions.every((item) => item.closest("dl") === term.closest("dl"))).toBe(true);
    expect(region.closest("dl")).toBeNull();
  });
});
