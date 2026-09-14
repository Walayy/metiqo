"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Button, IconButton } from "@metiquo/ui";
import { Check, Laptop, Moon, Palette, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribeToMount = () => () => undefined;

const themeOptions = [
  { icon: Laptop, label: "Système", value: "system" },
  { icon: Sun, label: "Clair", value: "light" },
  { icon: Moon, label: "Sombre", value: "dark" },
] as const;

export function ThemeMenu({
  ariaLabel = "Changer le thème",
  showLabel = false,
}: Readonly<{ ariaLabel?: string; showLabel?: boolean }>) {
  const { setTheme, theme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribeToMount,
    () => true,
    () => false,
  );
  const themeLabel = mounted
    ? (themeOptions.find((option) => option.value === theme)?.label ?? "Système")
    : "…";

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        {showLabel ? (
          <Button aria-label={ariaLabel} variant="outline">
            <Palette aria-hidden="true" className="size-5" strokeWidth={1.8} />
            <span className="min-w-28 text-left">Thème : {themeLabel}</span>
          </Button>
        ) : (
          <IconButton aria-label={ariaLabel}>
            <Palette aria-hidden="true" className="size-5" strokeWidth={1.8} />
          </IconButton>
        )}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="metiquo-menu-content min-w-44 p-1"
          sideOffset={8}
        >
          <DropdownMenu.Label className="px-2.5 py-1.5 text-xs font-semibold uppercase tracking-widest text-ink-secondary">
            Apparence
          </DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={theme ?? "system"} onValueChange={setTheme}>
            {themeOptions.map((option) => {
              const Icon = option.icon;

              return (
                <DropdownMenu.RadioItem
                  className="metiquo-menu-item justify-start"
                  key={option.value}
                  value={option.value}
                >
                  <Icon aria-hidden="true" className="size-4" strokeWidth={1.8} />
                  {option.label}
                  <span className="ml-auto flex size-4 items-center">
                    <DropdownMenu.ItemIndicator>
                      <Check aria-hidden="true" className="size-4" />
                    </DropdownMenu.ItemIndicator>
                  </span>
                </DropdownMenu.RadioItem>
              );
            })}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
