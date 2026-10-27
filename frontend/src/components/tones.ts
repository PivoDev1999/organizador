/** Color sets shared by badges and charts. Text colors keep at least 4.5:1 on their backgrounds. */
export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const TONE_STYLES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-800",
  info: "bg-sky-100 text-sky-900",
  success: "bg-emerald-100 text-emerald-900",
  warning: "bg-amber-100 text-amber-900",
  danger: "bg-red-100 text-red-800",
};
