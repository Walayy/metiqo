import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./button";

describe("Button", () => {
  it("is reachable and activatable with the keyboard", async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    render(<Button onClick={handleClick}>Créer une analyse</Button>);

    const button = screen.getByRole("button", { name: "Créer une analyse" });
    expect(button).toHaveAttribute("type", "button");

    await user.tab();
    expect(button).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it("preserves native disabled semantics", () => {
    render(<Button disabled>Action indisponible</Button>);

    expect(screen.getByRole("button", { name: "Action indisponible" })).toBeDisabled();
  });
});
