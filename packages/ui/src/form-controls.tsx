"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import {
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentPropsWithRef,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type OptionHTMLAttributes,
  type ReactNode,
} from "react";

import { cn } from "./lib/cn";

export function Input({ className, ...properties }: ComponentPropsWithRef<"input">) {
  return <input className={cn("metiquo-input", className)} {...properties} />;
}

export function Textarea({ className, ...properties }: ComponentPropsWithRef<"textarea">) {
  return <textarea className={cn("metiquo-input metiquo-textarea", className)} {...properties} />;
}

export function Radio({ className, ...properties }: Omit<ComponentPropsWithRef<"input">, "type">) {
  return <input className={cn("metiquo-radio", className)} type="radio" {...properties} />;
}

export function ToggleGroup({ className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("metiquo-toggle-group", className)} role="group" {...properties} />;
}

interface SelectOption {
  disabled: boolean;
  label: string;
  value: string;
}

function optionText(children: ReactNode): string {
  return Children.toArray(children)
    .map((child): string => {
      if (typeof child === "string" || typeof child === "number") return String(child);
      if (isValidElement<{ children?: ReactNode }>(child)) return optionText(child.props.children);
      return "";
    })
    .join("");
}

function readOptions(children: ReactNode, groupDisabled = false): SelectOption[] {
  return Children.toArray(children).flatMap((child): SelectOption[] => {
    if (!isValidElement<OptionHTMLAttributes<HTMLOptionElement>>(child)) return [];
    if (child.type === Fragment || child.type === "optgroup") {
      return readOptions(child.props.children, groupDisabled || Boolean(child.props.disabled));
    }
    if (child.type !== "option") return [];
    const label = child.props.label ?? optionText(child.props.children);
    return [
      {
        disabled: groupDisabled || Boolean(child.props.disabled),
        label,
        value: String(child.props.value ?? label),
      },
    ];
  });
}

export type SelectProperties = Omit<
  ComponentPropsWithRef<typeof SelectPrimitive.Trigger>,
  "asChild" | "children" | "defaultValue" | "name" | "onChange" | "type" | "value"
> & {
  autoComplete?: InputHTMLAttributes<HTMLInputElement>["autoComplete"];
  children: ReactNode;
  defaultValue?: string;
  form?: string;
  name?: string;
  onValueChange?: (value: string) => void;
  required?: boolean;
  value?: string;
};

/** Single-select with native option values and form behavior, including the empty value. */
export function Select({
  autoComplete,
  children,
  className,
  defaultValue,
  disabled,
  form,
  name,
  onValueChange,
  required,
  value,
  ...triggerProperties
}: SelectProperties) {
  const options = readOptions(children);
  const initialValue = defaultValue ?? options.find((option) => !option.disabled)?.value ?? "";
  const [uncontrolledValue, setUncontrolledValue] = useState(initialValue);
  const [open, setOpen] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const errorId = useId();
  const currentValue = value ?? uncontrolledValue;
  const requiredInvalid = Boolean(invalid && required && currentValue === "");
  const currentLabel =
    options.find((option) => option.value === currentValue)?.label ?? currentValue;
  const nativeSelect = useRef<HTMLSelectElement>(null);
  const triggerWrapper = useRef<HTMLSpanElement>(null);
  const focusAfterClose = useRef<HTMLElement | null>(null);

  function updateValue(nextValue: string) {
    if (value === undefined) setUncontrolledValue(nextValue);
    setInvalid(false);
    if (nextValue !== currentValue) onValueChange?.(nextValue);
  }

  useEffect(() => {
    const ownerForm = nativeSelect.current?.form;
    if (!ownerForm) return;
    function reset() {
      if (value === undefined) setUncontrolledValue(initialValue);
      setInvalid(false);
    }
    ownerForm.addEventListener("reset", reset);
    return () => {
      ownerForm.removeEventListener("reset", reset);
    };
  }, [initialValue, value, form]);

  return (
    <span className="metiquo-select" ref={triggerWrapper}>
      <SelectPrimitive.Root
        {...(disabled === undefined ? {} : { disabled })}
        open={open}
        onOpenChange={setOpen}
        onValueChange={(nextValue) => {
          updateValue(nextValue.slice("option:".length));
        }}
        value={`option:${currentValue}`}
      >
        <SelectPrimitive.Trigger
          aria-required={required ? true : undefined}
          className={cn("metiquo-input metiquo-select-trigger", className)}
          {...triggerProperties}
          aria-describedby={
            [triggerProperties["aria-describedby"], requiredInvalid ? errorId : undefined]
              .filter(Boolean)
              .join(" ") || undefined
          }
          aria-invalid={requiredInvalid ? true : triggerProperties["aria-invalid"]}
        >
          <SelectPrimitive.Value>{currentLabel}</SelectPrimitive.Value>
          <SelectPrimitive.Icon className="metiquo-select-chevron">
            <svg aria-hidden="true" fill="none" viewBox="0 0 20 20">
              <path
                d="m6 8 4 4 4-4"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
              />
            </svg>
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            align="start"
            className="metiquo-select-content"
            collisionPadding={12}
            onCloseAutoFocus={(event) => {
              if (focusAfterClose.current) {
                event.preventDefault();
                focusAfterClose.current.focus();
                focusAfterClose.current = null;
              }
            }}
            onKeyDown={(event) => {
              // Radix traps Tab by default. A form select should let users continue to adjacent fields.
              if (event.key !== "Tab") return;
              event.preventDefault();
              const trigger = triggerWrapper.current?.querySelector("button");
              const controls = Array.from(
                document.querySelectorAll<HTMLElement>(
                  'a[href], button, input:not([type="hidden"]), select, textarea, summary, [tabindex]',
                ),
              ).filter((element) => {
                let ancestor: HTMLElement | null = element;
                while (ancestor) {
                  const style = getComputedStyle(ancestor);
                  if (style.display === "none" || style.visibility === "hidden") return false;
                  if (
                    ancestor instanceof HTMLDetailsElement &&
                    !ancestor.open &&
                    !ancestor.querySelector(":scope > summary")?.contains(element)
                  )
                    return false;
                  ancestor = ancestor.parentElement;
                }
                return (
                  element.tabIndex >= 0 &&
                  !element.matches(":disabled") &&
                  !element.closest("[hidden], [inert], [data-radix-focus-guard]") &&
                  !event.currentTarget.contains(element)
                );
              });
              const index = trigger ? controls.indexOf(trigger) : -1;
              focusAfterClose.current =
                controls[index + (event.shiftKey ? -1 : 1)] ?? trigger ?? null;
              setOpen(false);
            }}
            position="popper"
            sideOffset={6}
          >
            <SelectPrimitive.ScrollUpButton
              className="metiquo-select-scroll"
              aria-label="Options précédentes"
            >
              ⌃
            </SelectPrimitive.ScrollUpButton>
            <SelectPrimitive.Viewport className="metiquo-select-viewport">
              {options.map((option) => (
                <SelectPrimitive.Item
                  className="metiquo-select-option"
                  disabled={option.disabled}
                  key={option.value}
                  textValue={option.label}
                  value={`option:${option.value}`}
                >
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="metiquo-select-indicator">
                    <svg aria-hidden="true" fill="none" viewBox="0 0 20 20">
                      <path
                        d="m5 10 3 3 7-7"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.6"
                      />
                    </svg>
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
            <SelectPrimitive.ScrollDownButton
              className="metiquo-select-scroll"
              aria-label="Options suivantes"
            >
              ⌄
            </SelectPrimitive.ScrollDownButton>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
      <select
        aria-hidden="true"
        autoComplete={autoComplete}
        className="metiquo-select-native"
        disabled={disabled}
        form={form}
        name={name}
        onChange={(event) => {
          updateValue(event.currentTarget.value);
        }}
        onInvalid={(event) => {
          event.preventDefault();
          setInvalid(true);
          triggerWrapper.current?.querySelector("button")?.focus();
        }}
        ref={nativeSelect}
        required={required}
        tabIndex={-1}
        value={currentValue}
      >
        {children}
      </select>
      {requiredInvalid ? (
        <span className="metiquo-field-error" id={errorId} role="alert">
          Veuillez sélectionner une option.
        </span>
      ) : null}
    </span>
  );
}
