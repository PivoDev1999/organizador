import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  agendaKeys,
  createEvent,
  deleteEvent,
  getCalendar,
  getEvent,
  listEventOccurrences,
  updateEvent,
  type DateRange,
} from "@/api/agenda";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import type { AgendaEvent, EventCreate, EventUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

export function useCalendar(range: DateRange) {
  return useQuery({
    queryKey: agendaKeys.calendar(range),
    queryFn: () => getCalendar(range),
    // Changing months keeps the previous grid on screen while the next one loads.
    placeholderData: keepPreviousData,
  });
}

export function useEventOccurrences(range: DateRange) {
  return useQuery({ queryKey: agendaKeys.occurrences(range), queryFn: () => listEventOccurrences(range) });
}

/**
 * The calendar only carries a summary of each event: the form loads the whole record. Always fetched
 * again on open (never from a cached copy): the PATCH sends every field, so a stale copy would undo
 * changes saved meanwhile (e.g. from "Próximos" or another device).
 */
export function useEvent(id: string) {
  return useQuery({ queryKey: agendaKeys.event(id), queryFn: () => getEvent(id), refetchOnMount: "always" });
}

/** Events feed the calendar, the "Próximos" list and the dashboard's agenda card: refresh them all. */
function useRefreshAgenda() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: agendaKeys.events }),
      queryClient.invalidateQueries({ queryKey: agendaKeys.calendarAll }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

/** Drops the cached copy of one event: the next form opens with what the API has. */
function useForgetEvent() {
  const queryClient = useQueryClient();
  return (id: string) => queryClient.removeQueries({ queryKey: agendaKeys.event(id) });
}

export function useSaveEvent(event: AgendaEvent | null) {
  const refresh = useRefreshAgenda();
  const forget = useForgetEvent();
  const done = () => {
    if (event) forget(event.id);
    return refresh();
  };
  return useMutation({
    mutationFn: (body: EventCreate & EventUpdate) => (event ? updateEvent(event.id, body) : createEvent(body)),
    onSuccess: done,
    // Deleted on another device: the form closes and the lists drop it.
    onError: (error) => (isNotFound(error) ? done() : undefined),
  });
}

/** What the delete dialog needs: an event from the calendar summary or the whole record. */
export interface EventToDelete {
  id: string;
  title: string;
  recurrence: AgendaEvent["recurrence"];
}

export function useDeleteEvent() {
  const refresh = useRefreshAgenda();
  const forget = useForgetEvent();
  const toast = useToast();
  return useMutation({
    mutationFn: (event: EventToDelete) => deleteEvent(event.id),
    onSuccess: () => toast.success("Compromisso excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: (_data, _error, event) => {
      forget(event.id);
      return refresh();
    },
  });
}
