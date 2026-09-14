import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { IconButton } from "./button";
import { Input, Select, ToggleGroup } from "./form-controls";

beforeAll(() => {
  // jsdom does not implement layout/scroll and pointer capture used by Radix.
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.hasPointerCapture = () => false;
  HTMLElement.prototype.releasePointerCapture = vi.fn();
});

afterEach(cleanup);

const options = (
  <>
    <option value="">Tous</option>
    <option value="alpha">Alpha</option>
    <option disabled value="beta">
      Beta indisponible
    </option>
    <option value="charlie">Charlie</option>
    <option value="delta">Delta</option>
  </>
);

describe("Select", () => {
  it("uses an accessible label and supports arrows, Home/End, selection and Escape", async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(
      <label htmlFor="grade">
        Grade
        <Select id="grade" onValueChange={onValueChange}>
          {options}
        </Select>
      </label>,
    );
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Tous" })).toHaveFocus();
    });
    await user.keyboard("{End}");
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Delta" })).toHaveFocus();
    });
    await user.keyboard("{Home}{ArrowDown}{ArrowDown}");
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Charlie" })).toHaveFocus();
    });
    await user.keyboard("{Enter}");
    expect(onValueChange).toHaveBeenLastCalledWith("charlie");
    expect(trigger).toHaveTextContent("Charlie");
    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });
    await user.keyboard("{ArrowUp}{Home}{Escape}");
    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger).toHaveTextContent("Charlie");
    expect(onValueChange).toHaveBeenCalledOnce();
  });

  it("supports typeahead and pointer selection", async () => {
    const user = userEvent.setup();
    render(<Select aria-label="Grade">{options}</Select>);
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.click(trigger);
    await user.keyboard("del");
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Delta" })).toHaveFocus();
    });
    await user.keyboard("{Enter}");
    expect(trigger).toHaveTextContent("Delta");
    await user.click(trigger);
    await user.click(screen.getByRole("option", { name: "Alpha" }));
    expect(trigger).toHaveTextContent("Alpha");
  });

  it("lets Tab and Shift+Tab close the menu and move between form controls", async () => {
    const user = userEvent.setup();
    render(
      <form>
        <Input aria-label="Avant" />
        <div style={{ display: "none" }}>
          <button type="button">Lien mobile masqué</button>
        </div>
        <Select aria-label="Grade">{options}</Select>
        <div style={{ display: "none" }}>
          <button type="button">Lien masqué</button>
        </div>
        <Input aria-label="Après" />
      </form>,
    );
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.click(trigger);
    await user.tab();
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Après" })).toHaveFocus();
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    await user.click(trigger);
    await user.tab({ shift: true });
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Avant" })).toHaveFocus();
    });
    expect(trigger).toHaveTextContent("Tous");
  });

  it("submits real option values including empty filters and resets an uncontrolled field", async () => {
    const user = userEvent.setup();
    let submittedValues: FormDataEntryValue[] = [];
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submittedValues = new FormData(event.currentTarget).getAll("grade");
        }}
      >
        <Select aria-label="Grade" defaultValue="alpha" name="grade">
          {options}
        </Select>
        <button type="submit">Appliquer</button>
        <button type="reset">Réinitialiser</button>
      </form>,
    );
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(submittedValues).toEqual(["alpha"]);
    await user.click(trigger);
    await user.click(screen.getByRole("option", { name: "Tous" }));
    await user.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(submittedValues).toEqual([""]);
    await user.click(screen.getByRole("button", { name: "Réinitialiser" }));
    expect(trigger).toHaveTextContent("Alpha");
    await user.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(submittedValues).toEqual(["alpha"]);
  });

  it("includes disclosure summaries in the tab order while skipping collapsed contents", async () => {
    const user = userEvent.setup();
    render(
      <>
        <details>
          <summary>Explication précédente</summary>
          <button type="button">Action précédente masquée</button>
        </details>
        <Select aria-label="Grade">{options}</Select>
        <details>
          <summary>Explication suivante</summary>
          <button type="button">Action suivante masquée</button>
        </details>
      </>,
    );
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.click(trigger);
    await user.tab();
    await waitFor(() => {
      expect(screen.getByText("Explication suivante")).toHaveFocus();
    });
    await user.click(trigger);
    await user.tab({ shift: true });
    await waitFor(() => {
      expect(screen.getByText("Explication précédente")).toHaveFocus();
    });
  });

  it("follows controlled changes and preserves required/disabled native form behavior", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    const { rerender } = render(
      <form onSubmit={submit}>
        <Select aria-label="Grade" name="grade" required value="">
          {options}
        </Select>
        <button type="submit">Appliquer</button>
      </form>,
    );
    const trigger = screen.getByRole("combobox", { name: "Grade" });
    await user.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(submit).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-invalid", "true");
    expect(trigger).toHaveAccessibleDescription("Veuillez sélectionner une option.");
    expect(screen.getByRole("alert")).toHaveTextContent("Veuillez sélectionner une option.");
    rerender(
      <form>
        <Select aria-label="Grade" name="grade" required value="delta">
          {options}
        </Select>
      </form>,
    );
    expect(trigger).toHaveTextContent("Delta");
    expect(trigger).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(
      <form>
        <Select aria-label="Grade" disabled name="grade" required value="delta">
          {options}
        </Select>
      </form>,
    );
    expect(screen.getByRole("combobox", { name: "Grade" })).toBeDisabled();
  });

  it("preserves native form change and autofill updates", () => {
    const onValueChange = vi.fn();
    const { container } = render(
      <Select aria-label="Grade" name="grade" onValueChange={onValueChange}>
        {options}
      </Select>,
    );
    const native = container.querySelector('select[name="grade"]');
    if (!native) throw new Error("Native form control missing");
    fireEvent.change(native, { target: { value: "charlie" } });
    expect(onValueChange).toHaveBeenCalledWith("charlie");
    expect(screen.getByRole("combobox", { name: "Grade" })).toHaveTextContent("Charlie");
  });
});

describe("IconButton", () => {
  it("exposes a quiet selection state and remains keyboard-operable", async () => {
    const user = userEvent.setup();
    const activate = vi.fn();
    render(
      <ToggleGroup aria-label="Affichage">
        <IconButton active aria-label="Liste" onClick={activate}>
          ≡
        </IconButton>
        <IconButton aria-label="Grille">⊞</IconButton>
      </ToggleGroup>,
    );
    const active = screen.getByRole("button", { name: "Liste", pressed: true });
    await user.tab();
    await user.keyboard(" ");
    expect(active).toHaveFocus();
    expect(activate).toHaveBeenCalledOnce();
  });
});
