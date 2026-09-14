"use client";

import { Button } from "@metiquo/ui";
import { useId, useState } from "react";
import { ObservedOddsDashboard } from "./observed-odds-dashboard";
import { StakeOddsDashboard } from "./stake-odds-dashboard";

export function OddsDashboard() {
  const [source, setSource] = useState("stake");
  const id = useId();
  const sources = [
    { value: "stake", label: "Marchés Stake" },
    { value: "history", label: "Relevés de vainqueurs" },
  ];
  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-2">
        <p className="ui-eyebrow">Prix observés</p>
        <h1 className="ui-page-title">Cotes</h1>
        <p className="text-body text-ink-secondary">
          Consultez les prix collectés, leur source et leur fraîcheur. Une cote observée ne
          constitue pas une opportunité validée.
        </p>
      </header>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Source des cotes">
        {sources.map((item, index) => (
          <Button
            key={item.value}
            id={`${id}-${item.value}-tab`}
            role="tab"
            aria-controls={`${id}-${item.value}-panel`}
            aria-selected={source === item.value}
            tabIndex={source === item.value ? 0 : -1}
            variant={source === item.value ? "primary" : "outline"}
            onClick={() => {
              setSource(item.value);
            }}
            onKeyDown={(event) => {
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? sources.length - 1
                    : event.key === "ArrowRight"
                      ? (index + 1) % sources.length
                      : event.key === "ArrowLeft"
                        ? (index + sources.length - 1) % sources.length
                        : null;
              if (next === null) return;
              event.preventDefault();
              event.currentTarget.parentElement
                ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
                .item(next)
                .focus();
            }}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {sources.map((item) => (
        <div
          key={item.value}
          id={`${id}-${item.value}-panel`}
          role="tabpanel"
          aria-labelledby={`${id}-${item.value}-tab`}
          hidden={source !== item.value}
          tabIndex={0}
        >
          {source === item.value ? (
            item.value === "stake" ? (
              <StakeOddsDashboard />
            ) : (
              <ObservedOddsDashboard />
            )
          ) : null}
        </div>
      ))}
    </div>
  );
}
