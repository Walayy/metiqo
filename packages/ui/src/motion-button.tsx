"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ComponentProps } from "react";

import { buttonVariants } from "./button";
import { cn } from "./lib/cn";

type MotionButtonProperties = Omit<
  ComponentProps<typeof motion.button>,
  "transition" | "whileHover" | "whileTap"
> & {
  variant?: "ghost" | "outline" | "primary";
};

export function MotionButton({
  className,
  type = "button",
  variant = "primary",
  ...properties
}: MotionButtonProperties) {
  const shouldReduceMotion = useReducedMotion();
  const interaction = shouldReduceMotion
    ? { transition: { duration: 0 } }
    : {
        transition: { duration: 0.16 },
        whileHover: { y: -1 },
        whileTap: { scale: 0.98 },
      };

  return (
    <motion.button
      className={cn(buttonVariants({ variant }), className)}
      {...interaction}
      type={type}
      {...properties}
    />
  );
}
