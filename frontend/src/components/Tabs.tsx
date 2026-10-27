import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabItem<T extends string> {
  value: T;
  label: string;
}

export interface TabsProps<T extends string> {
  label: string;
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  /** Content of the selected tab. */
  children: ReactNode;
}

/** WAI-ARIA tabs: arrow keys move between tabs, only the selected one is in the tab order. */
export function Tabs<T extends string>({ label, tabs, value, onChange, children }: TabsProps<T>) {
  const baseId = useId();
  const refs = useRef(new Map<T, HTMLButtonElement>());

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.value === value);
    const moves: Record<string, number> = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const target = tabs[next];
    if (!target) return;
    onChange(target.value);
    refs.current.get(target.value)?.focus();
  }

  return (
    <div>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="mb-4 flex gap-1 border-b border-slate-200">
        {tabs.map((tab) => {
          const selected = tab.value === value;
          return (
            <button
              key={tab.value}
              ref={(element) => {
                if (element) refs.current.set(tab.value, element);
                else refs.current.delete(tab.value);
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.value}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.value)}
              className={cn(
                "-mb-px min-h-11 border-b-2 px-4 font-medium",
                selected ? "border-brand-700 text-brand-800" : "border-transparent text-slate-700 hover:text-slate-900",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-tab-${value}`}>
        {children}
      </div>
    </div>
  );
}
