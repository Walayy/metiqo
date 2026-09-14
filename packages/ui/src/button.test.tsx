import { fireEvent, render, screen } from "@testing-library/react";
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

  it("keeps an aria-disabled action focusable without clicking or submitting", async () => {
    const user = userEvent.setup();
    const activate = vi.fn();
    const submit = vi.fn((event: { preventDefault: () => void }) => {
      event.preventDefault();
    });
    render(
      <form onSubmit={submit}>
        <Button aria-disabled type="submit" onClick={activate}>
          Chargement…
        </Button>
      </form>,
    );
    const button = screen.getByRole("button", { name: "Chargement…" });
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter} ");
    await user.click(button);
    expect(activate).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
    expect(button).toHaveFocus();
  });

  it("prevents a disabled link button from navigating or activating its child handler", async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();
    render(
      <>
        <Button asChild disabled>
          <a href="/restricted" onClick={handleClick}>
            Accès indisponible
          </a>
        </Button>
        <Button>Action suivante</Button>
      </>,
    );

    const link = screen.getByRole("link", { name: "Accès indisponible" });
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(fireEvent.click(link)).toBe(false);
    expect(handleClick).not.toHaveBeenCalled();
    await user.tab();
    expect(screen.getByRole("button", { name: "Action suivante" })).toHaveFocus();
  });
});
