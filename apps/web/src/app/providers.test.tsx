import { useQueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Providers } from "./providers";

function QueryClientProbe() {
  const queryClient = useQueryClient();

  return <output>{queryClient.getDefaultOptions().queries?.staleTime?.toString()}</output>;
}

describe("Providers", () => {
  it("makes the configured TanStack Query client available", () => {
    render(
      <Providers>
        <QueryClientProbe />
      </Providers>,
    );

    expect(screen.getByText("30000")).toBeInTheDocument();
  });
});
