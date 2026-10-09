import type { Member } from "@/lib/types";
import { shortId } from "@/lib/format";

export type People = Map<string, Member>;

export function peopleIndex(members: Member[] | undefined): People {
  return new Map((members ?? []).map((m) => [m.user_id, m]));
}

export function personName(people: People, id: string | null | undefined): string {
  if (!id) return "—";
  return people.get(id)?.full_name ?? `User ${shortId(id)}`;
}

export const ROLES = [
  "HSE_MANAGER",
  "PROJECT_MANAGER",
  "SAFETY_ENGINEER",
  "QA_QC_ENGINEER",
  "SITE_ENGINEER",
  "ORG_ADMIN",
] as const;
