import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardContent, CardTitle } from "./card";

describe("Card", () => {
  it("keeps semantic section and heading structure", () => {
    render(
      <Card aria-labelledby="health-title">
        <CardTitle id="health-title">Santé des données</CardTitle>
        <CardContent>À jour</CardContent>
      </Card>,
    );

    expect(screen.getByRole("region", { name: "Santé des données" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Santé des données", level: 2 }),
    ).toBeInTheDocument();
  });
});
