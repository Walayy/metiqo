import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusList, Table, TableBody, TableCell, TableCellContent, TableRow } from "./table";

describe("Table", () => {
  it("preserves table navigation and complete content when cells include responsive labels", () => {
    render(
      <Table
        aria-label="Marchés"
        columns={[
          { label: "Match", variant: "identity" },
          { label: "Cote", variant: "number" },
          { label: "Snapshot", variant: "technical" },
        ]}
      >
        <TableBody>
          <TableRow>
            <TableCell label="Match" variant="identity">
              <TableCellContent
                primary="Aurore 11 · Bastion 11"
                secondary="Dernière cote reçue par le serveur."
              />
            </TableCell>
            <TableCell label="Cote" variant="number">
              3,60
            </TableCell>
            <TableCell label="Snapshot" variant="technical">
              b698a58d-f10f-5ff4-8833-9eec45bc8100
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    const table = screen.getByRole("table", { name: "Marchés" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByRole("cell", { name: "3,60" })).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", { name: "b698a58d-f10f-5ff4-8833-9eec45bc8100" }),
    ).toBeInTheDocument();
    expect(within(table).getByText("Dernière cote reçue par le serveur.")).toBeVisible();
    expect(screen.getByRole("region", { name: "Marchés" })).toHaveAttribute("tabindex", "0");
  });

  it("keeps each secondary gate and its text state available without depending on color", () => {
    render(
      <StatusList
        aria-label="Gates"
        items={[
          { label: "label", value: "ok", tone: "success" },
          { label: "model", value: "attente", tone: "warning" },
          { label: "mapping", value: "non", tone: "danger" },
        ]}
      />,
    );

    const list = screen.getByRole("list", { name: "Gates" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["label: ok", "model: attente", "mapping: non"]);
  });
});
