import { Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { fieldBorder, fieldClass } from "./fieldStyles";

export interface SearchFieldProps {
  label: string;
  /** Committed value (e.g. from the URL). Outside changes (back button) replace what is typed. */
  value: string;
  /** Called with the trimmed text, `delay` ms after the user stops typing (at once when clearing). */
  onSearch: (value: string) => void;
  placeholder?: string;
  delay?: number;
  className?: string;
}

/** Search input with debounce, so each keystroke does not hit the API. */
export function SearchField({ label, value, onSearch, placeholder, delay = 300, className }: SearchFieldProps) {
  const id = useId();
  const [text, setText] = useState(value);
  const [committed, setCommitted] = useState(value);
  const onSearchRef = useRef(onSearch);

  useEffect(() => {
    onSearchRef.current = onSearch;
  }, [onSearch]);

  // A new value from outside (navigation) wins over the local text.
  if (value !== committed) {
    setCommitted(value);
    setText(value);
  }

  useEffect(() => {
    const trimmed = text.trim();
    if (trimmed === committed.trim()) return;
    const timer = setTimeout(() => onSearchRef.current(trimmed), delay);
    return () => clearTimeout(timer);
  }, [text, committed, delay]);

  return (
    <div className={cn("space-y-1", className)}>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {label}
      </label>
      <div className="relative">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-500" />
        <input
          id={id}
          type="search"
          value={text}
          placeholder={placeholder}
          onChange={(event) => setText(event.target.value)}
          className={cn(fieldClass, fieldBorder(false), "pr-10 pl-9 [&::-webkit-search-cancel-button]:hidden")}
        />
        {text && (
          <button
            type="button"
            onClick={() => {
              setText("");
              onSearchRef.current("");
            }}
            className="absolute top-1/2 right-1 -translate-y-1/2 rounded-md p-2 text-slate-600 hover:bg-slate-100"
            aria-label="Limpar busca"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
