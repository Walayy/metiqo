import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { OddsDashboard } from "./odds-dashboard";

vi.mock("./stake-odds-dashboard", () => ({
  StakeOddsDashboard: () => <p>Marchés collectés</p>,
}));
vi.mock("./observed-odds-dashboard", () => ({
  ObservedOddsDashboard: () => <p>Relevés enregistrés</p>,
}));

afterEach(cleanup);

it("provides named source panels and manual keyboard activation without loading every source", () => {
  render(<OddsDashboard />);
  const stake = screen.getByRole("tab", { name: "Marchés Stake" });
  const history = screen.getByRole("tab", { name: "Relevés de vainqueurs" });
  expect(screen.getByRole("heading", { name: "Cotes", level: 1 })).toBeVisible();
  expect(screen.getByRole("tabpanel", { name: "Marchés Stake" })).toHaveTextContent(
    "Marchés collectés",
  );
  expect(history).toHaveAttribute("aria-selected", "false");
  stake.focus();
  fireEvent.keyDown(stake, { key: "ArrowRight" });
  expect(history).toHaveFocus();
  expect(screen.queryByText("Relevés enregistrés")).not.toBeInTheDocument();
  fireEvent.click(history);
  expect(history).toHaveAttribute("aria-selected", "true");
  expect(history).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tabpanel", { name: "Relevés de vainqueurs" })).toHaveTextContent(
    "Relevés enregistrés",
  );
  expect(screen.queryByText("Marchés collectés")).not.toBeInTheDocument();
  fireEvent.keyDown(history, { key: "Home" });
  expect(stake).toHaveFocus();
  fireEvent.keyDown(stake, { key: "ArrowLeft" });
  expect(history).toHaveFocus();
});
