import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PagedResults } from "./paged-results";

describe("PagedResults", () => {
  it("preserves the focused control and final count after loading the last page", () => {
    const query = {
      data: { data: [1, 2], page: { offset: 0, total: 3 } },
      error: null,
      hasNextPage: true,
      isFetching: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn().mockResolvedValue(undefined),
    };
    const { rerender } = render(<PagedResults label="de résultats" query={query} />);
    const button = screen.getByRole("button", { name: "Afficher plus de résultats" });
    button.focus();
    fireEvent.click(button);
    rerender(
      <PagedResults
        label="de résultats"
        query={{ ...query, isFetching: true, isFetchingNextPage: true }}
      />,
    );
    expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(query.fetchNextPage).toHaveBeenCalledOnce();
    rerender(
      <PagedResults
        label="de résultats"
        query={{
          ...query,
          data: { data: [1, 2, 3], page: { offset: 0, total: 3 } },
          hasNextPage: false,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("3 résultats affichés sur 3");
    expect(button).toHaveTextContent("Tous les résultats sont affichés");
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(button);
    expect(query.fetchNextPage).toHaveBeenCalledOnce();
  });
});
