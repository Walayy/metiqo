"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, MouseEvent } from "react";

import { cn } from "./lib/cn";

const buttonVariants = cva("metiquo-button", {
  defaultVariants: {
    size: "default",
    variant: "primary",
  },
  variants: {
    size: {
      default: "metiquo-button--default",
      icon: "metiquo-button--icon",
      small: "metiquo-button--small",
    },
    variant: {
      ghost: "metiquo-button--ghost",
      outline: "metiquo-button--outline",
      primary: "metiquo-button--primary",
      secondary: "metiquo-button--secondary",
    },
  },
});

export type ButtonProperties = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

export function Button({
  asChild = false,
  className,
  disabled,
  onClickCapture,
  size,
  type = "button",
  variant,
  ...properties
}: ButtonProperties) {
  const classes = cn(buttonVariants({ size, variant }), className);
  function captureClick(event: MouseEvent<HTMLButtonElement>) {
    if (
      disabled ||
      properties["aria-disabled"] === true ||
      properties["aria-disabled"] === "true"
    ) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    onClickCapture?.(event);
  }

  if (asChild) {
    return (
      <Slot
        className={classes}
        {...properties}
        aria-disabled={disabled ? true : properties["aria-disabled"]}
        onClickCapture={captureClick}
        tabIndex={disabled ? -1 : properties.tabIndex}
      />
    );
  }

  return (
    <button
      className={classes}
      disabled={disabled}
      onClickCapture={captureClick}
      type={type}
      {...properties}
    />
  );
}

export type IconButtonProperties = Omit<ButtonProperties, "size"> & {
  active?: boolean;
  "aria-label": string;
};

export function IconButton({
  active,
  asChild,
  className,
  variant = "ghost",
  ...properties
}: IconButtonProperties) {
  return (
    <Button
      {...(asChild === undefined ? {} : { asChild })}
      aria-pressed={asChild ? undefined : active}
      className={cn("metiquo-icon-button", className)}
      data-active={active ? true : undefined}
      size="icon"
      variant={variant}
      {...properties}
    />
  );
}

export { buttonVariants };
