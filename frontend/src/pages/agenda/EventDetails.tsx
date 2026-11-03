import { MapPin, Repeat } from "lucide-react";
import type { EventRecurrence } from "@/api/types";
import { EVENT_RECURRENCE_LABELS } from "@/lib/labels";

/** Location and repetition of an event, as inline pieces of a details line (nothing when both are empty). */
export function EventDetails({ location, recurrence }: { location: string | null; recurrence: EventRecurrence }) {
  return (
    <>
      {location && (
        <span className="inline-flex items-center gap-1">
          <MapPin aria-hidden="true" className="size-4" />
          <span className="sr-only">Local:</span>
          {location}
        </span>
      )}
      {recurrence !== "none" && (
        <span className="inline-flex items-center gap-1">
          <Repeat aria-hidden="true" className="size-4" />
          Repete {EVENT_RECURRENCE_LABELS[recurrence].toLowerCase()}
        </span>
      )}
    </>
  );
}
