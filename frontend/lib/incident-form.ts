// Client-side checks for the new-incident form. They mirror IncidentIn in backend/app/api/schemas.py so people
// get feedback before submitting; the API validates again and remains the authority.
import { localInputToIso } from "./format";
import type { Domain, Severity } from "./types";

export interface IncidentForm {
  title: string;
  description: string;
  domain: Domain;
  severity: Severity;
  occurred_at: string;
  site_id: string;
  category: string;
  location: string;
  activity: string;
  people_involved: string;
  immediate_actions: string;
}

export function validateIncident(form: IncidentForm, now: number = Date.now()): Record<string, string> {
  const errors: Record<string, string> = {};
  const title = form.title.trim();
  const description = form.description.trim();
  if (title.length < 3 || title.length > 300) errors.title = "Title must be 3 to 300 characters.";
  if (description.length < 10 || description.length > 20000)
    errors.description = "Describe what happened in at least 10 characters.";
  const occurred = localInputToIso(form.occurred_at);
  if (!occurred) errors.occurred_at = "Enter when it happened.";
  else if (new Date(occurred).getTime() > now + 5 * 60 * 1000)
    errors.occurred_at = "The time it happened cannot be in the future.";
  const people = Number(form.people_involved);
  if (form.people_involved.trim() === "" || !Number.isInteger(people) || people < 0 || people > 10000)
    errors.people_involved = "Enter a whole number from 0 to 10000.";
  if (form.category.length > 80) errors.category = "Category is limited to 80 characters.";
  if (form.location.length > 300) errors.location = "Location is limited to 300 characters.";
  if (form.activity.length > 200) errors.activity = "Activity is limited to 200 characters.";
  if (form.immediate_actions.length > 5000) errors.immediate_actions = "Limited to 5000 characters.";
  return errors;
}

/** The IncidentIn request body; empty optional fields are sent as null. */
export function toIncidentBody(form: IncidentForm) {
  const optional = (value: string) => (value.trim() ? value.trim() : null);
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    domain: form.domain,
    severity: form.severity,
    occurred_at: localInputToIso(form.occurred_at),
    site_id: form.site_id || null,
    category: optional(form.category),
    location: optional(form.location),
    activity: optional(form.activity),
    people_involved: Number(form.people_involved),
    immediate_actions: optional(form.immediate_actions),
  };
}
