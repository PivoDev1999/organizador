export const fieldClass =
  "block w-full min-h-11 rounded-lg border bg-white px-3 text-base text-slate-900 placeholder:text-slate-500 " +
  "focus:border-brand-700 focus:outline-2 focus:outline-offset-0 focus:outline-brand-700 disabled:bg-slate-100";

export const fieldBorder = (invalid: boolean) =>
  invalid ? "border-red-700" : "border-slate-400";
