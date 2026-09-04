"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "./lib/cn";

const buttonVariants = cva(
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-[background-color,border-color,color,box-shadow,transform] duration-interaction ease-out select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none active:translate-y-px motion-reduce:active:translate-y-0",
  {
    defaultVariants: {
      size: "default",
      variant: "primary",
    },
    variants: {
      size: {
        default: "min-h-11 px-4",
        icon: "size-11 p-0",
        small: "min-h-9 px-3",
      },
      variant: {
        ghost: "bg-transparent text-ink-secondary hover:bg-surface-muted hover:text-ink-primary",
        outline:
          "border border-border-strong bg-surface-raised text-ink-primary hover:border-accent hover:bg-accent-soft",
        primary: "bg-accent text-accent-contrast shadow-sm hover:bg-accent-strong",
      },
    },
  },
);

export type ButtonProperties = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

export function Button({
  asChild = false,
  className,
  size,
  type = "button",
  variant,
  ...properties
}: ButtonProperties) {
  const classes = cn(buttonVariants({ size, variant }), className);

  if (asChild) {
    return <Slot className={classes} {...properties} />;
  }

  return <button className={classes} type={type} {...properties} />;
}

export { buttonVariants };
