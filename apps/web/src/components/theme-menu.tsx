"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Button } from "@metiquo/ui";
import { Laptop, Moon, Palette, Sun } from "lucide-react";
import { useTheme } from "next-themes";

const themeOptions = [
  { icon: Laptop, label: "Système", value: "system" },
  { icon: Sun, label: "Clair", value: "light" },
  { icon: Moon, label: "Sombre", value: "dark" },
] as const;

export function ThemeMenu() {
  const { setTheme } = useTheme();

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button aria-label="Changer le thème" size="icon" variant="ghost">
          <Palette aria-hidden="true" className="size-5" strokeWidth={1.8} />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="z-50 min-w-44 rounded-lg border border-border-subtle bg-surface-raised p-1.5 text-ink-primary shadow-panel"
          sideOffset={8}
        >
          <DropdownMenu.Label className="px-2.5 py-1.5 text-xs font-semibold uppercase tracking-widest text-ink-secondary">
            Apparence
          </DropdownMenu.Label>
          {themeOptions.map((option) => {
            const Icon = option.icon;

            return (
              <DropdownMenu.Item
                className="flex min-h-10 cursor-default items-center gap-3 rounded-md px-2.5 text-sm outline-none transition-colors duration-interaction focus:bg-accent-soft focus:text-ink-primary motion-reduce:transition-none"
                key={option.value}
                onSelect={() => {
                  setTheme(option.value);
                }}
              >
                <Icon aria-hidden="true" className="size-4" strokeWidth={1.8} />
                {option.label}
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
