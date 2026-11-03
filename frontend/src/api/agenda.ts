import { apiFetch } from "./client";
import type { AgendaEvent, CalendarItem, EventCreate, EventOccurrence, EventUpdate } from "./types";

/** Inclusive range of days, "YYYY-MM-DD" (at most 366 days: the API answers 422 past that). */
export interface DateRange {
  from: string;
  to: string;
}

export const agendaKeys = {
  /** Occurrence lists and single events: any event change touches them. */
  events: ["events"] as const,
  occurrences: (range: DateRange) => ["events", "list", range] as const,
  event: (id: string) => ["events", "detail", id] as const,
  /** Events, tasks, bills and pet reminders by day: changes in any of those modules touch it. */
  calendarAll: ["calendar"] as const,
  calendar: (range: DateRange) => ["calendar", range] as const,
};

/** Occurrences in the range (a recurring event shows up once per day), sorted by day and time. */
export function listEventOccurrences(range: DateRange): Promise<EventOccurrence[]> {
  return apiFetch("/api/events", { query: range });
}

export function getEvent(id: string): Promise<AgendaEvent> {
  return apiFetch("/api/events/{event_id}", { params: { event_id: id } });
}

export function createEvent(body: EventCreate): Promise<AgendaEvent> {
  return apiFetch("/api/events", { method: "post", json: body });
}

export function updateEvent(id: string, body: EventUpdate): Promise<AgendaEvent> {
  return apiFetch("/api/events/{event_id}", { method: "patch", params: { event_id: id }, json: body });
}

export function deleteEvent(id: string): Promise<undefined> {
  return apiFetch("/api/events/{event_id}", { method: "delete", params: { event_id: id } });
}

/** Everything that falls in the range, read-only: events, open tasks, unpaid bills and pet reminders. */
export function getCalendar(range: DateRange): Promise<CalendarItem[]> {
  return apiFetch("/api/calendar", { query: range });
}
