/**
 * Display constants and site copy.
 *
 * Entries used to live here. They live in PostgreSQL now and arrive through
 * `api.ts`; what stays is the vocabulary the interface uses to render them.
 */

import type { EntryType, Verdict } from "./api";

export type { Clock, CribSection, EntryType, GuideCard, GuideDetail, Verdict } from "./api";

export const VERDICTS: Verdict[] = ["yes", "kinda", "talk_only", "dont"];
export const TYPES: EntryType[] = ["scene", "taste", "role"];

/**
 * Three of the four are a yes. "TALK ONLY" replaced "NOT REALLY" because the
 * finding it describes - the conversation holds, the doing does not - is useful,
 * and the old wording read as a refusal on a site that exists to help.
 */
export const VERDICT_LABEL: Record<Verdict, string> = {
  yes: "YES",
  kinda: "KINDA",
  talk_only: "TALK ONLY",
  dont: "DON'T",
};

export const TYPE_GLYPH: Record<EntryType, string> = { scene: "◆", taste: "●", role: "▲" };

/** Fill level of the verdict gauge: full, half, low, stopped. */
export const VERDICT_LEVEL: Record<Verdict, number> = {
  yes: 1,
  kinda: 0.5,
  talk_only: 0.3,
  dont: 0,
};

export const VERDICT_TONE: Record<Verdict, string> = {
  yes: "yes",
  kinda: "kinda",
  talk_only: "talk",
  dont: "dont",
};
