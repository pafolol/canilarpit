/** Small form primitives shared by the guide editor. */

import type { ReactNode } from "react";
import type { CribSection, HardSpoiler, Phrase } from "../api";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="af">
      <span className="af__label">{label}</span>
      {children}
      {hint ? <span className="af__hint">{hint}</span> : null}
    </label>
  );
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  placeholder,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  hint?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        className="af__input"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  hint,
  min,
  disabled,
}: {
  label: string;
  value: number | null;
  onChange: (next: number | null) => void;
  hint?: string;
  min?: number;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        className="af__input"
        type="number"
        min={min}
        disabled={disabled}
        value={value ?? ""}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
    </Field>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  hint,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  hint?: string;
  rows?: number;
}) {
  return (
    <Field label={label} hint={hint}>
      <textarea
        className="af__input af__input--area"
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
  hint,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
  hint?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <select
        className="af__input"
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

/**
 * One paragraph or line per row. Empty rows are dropped on the way out, so an
 * editor can leave a blank box behind without breaking validation.
 */
export function ListField({
  label,
  values,
  onChange,
  hint,
  rows = 2,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  hint?: string;
  rows?: number;
}) {
  const update = (index: number, text: string) => {
    const next = [...values];
    next[index] = text;
    onChange(next);
  };

  return (
    <div className="af">
      <span className="af__label">{label}</span>
      {hint ? <span className="af__hint">{hint}</span> : null}
      <div className="af__list">
        {values.map((value, index) => (
          <div className="af__row" key={index}>
            <textarea
              className="af__input af__input--area"
              rows={rows}
              value={value}
              onChange={(event) => update(index, event.target.value)}
            />
            <button
              type="button"
              className="af__drop"
              aria-label={`Remove item ${index + 1}`}
              onClick={() => onChange(values.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <button type="button" className="af__add" onClick={() => onChange([...values, ""])}>
        Add
      </button>
    </div>
  );
}

export function CribEditor({
  sections,
  onChange,
}: {
  sections: CribSection[];
  onChange: (next: CribSection[]) => void;
}) {
  const replace = (index: number, section: CribSection) => {
    const next = [...sections];
    next[index] = section;
    onChange(next);
  };

  return (
    <div className="af">
      <span className="af__label">Crib sheet</span>
      <span className="af__hint">
        The block a reader copies. Each section is a heading and the lines under it.
      </span>
      {sections.map((section, index) => (
        <div className="af__crib" key={index}>
          <div className="af__row">
            <input
              className="af__input"
              value={section.heading}
              placeholder="Heading"
              onChange={(event) => replace(index, { ...section, heading: event.target.value })}
            />
            <button
              type="button"
              className="af__drop"
              aria-label={`Remove section ${index + 1}`}
              onClick={() => onChange(sections.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
          <ListField
            label="Lines"
            values={section.lines}
            rows={1}
            onChange={(lines) => replace(index, { ...section, lines })}
          />
        </div>
      ))}
      <button
        type="button"
        className="af__add"
        onClick={() => onChange([...sections, { heading: "", lines: [""] }])}
      >
        Add section
      </button>
    </div>
  );
}

/** Comma-separated in, trimmed list out. Good for aliases and flags. */
export function CsvField({
  label,
  values,
  onChange,
  hint,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  hint?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        className="af__input"
        value={values.join(", ")}
        onChange={(event) =>
          onChange(
            event.target.value
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
    </Field>
  );
}


export function PhraseEditor({
  phrases,
  onChange,
  disabled = false,
}: {
  phrases: Phrase[];
  onChange: (next: Phrase[]) => void;
  disabled?: boolean;
}) {
  const replace = (index: number, phrase: Phrase) => {
    const next = [...phrases];
    next[index] = phrase;
    onChange(next);
  };

  if (disabled) {
    return (
      <div className="af">
        <span className="af__label">Things to say</span>
        <span className="af__hint">A DON&rsquo;T entry hands out no lines.</span>
      </div>
    );
  }

  return (
    <div className="af">
      <span className="af__label">Things to say</span>
      <span className="af__hint">
        Sentences, not facts. Each one has to survive being said out loud by somebody
        who is bluffing.
      </span>
      {phrases.map((phrase, index) => (
        <div className="af__crib" key={index}>
          <div className="af__row">
            <input
              className="af__input"
              value={phrase.line}
              placeholder="The line, said verbatim"
              onChange={(event) => replace(index, { ...phrase, line: event.target.value })}
            />
            <button
              type="button"
              className="af__drop"
              aria-label={`Remove phrase ${index + 1}`}
              onClick={() => onChange(phrases.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
          <input
            className="af__input"
            value={phrase.when}
            placeholder="When to use it"
            onChange={(event) => replace(index, { ...phrase, when: event.target.value })}
          />
          <input
            className="af__input"
            value={phrase.invites ?? ""}
            placeholder="Optional: the follow-up it invites"
            onChange={(event) =>
              replace(index, { ...phrase, invites: event.target.value || null })
            }
          />
        </div>
      ))}
      <button
        type="button"
        className="af__add"
        onClick={() => onChange([...phrases, { line: "", when: "", invites: null }])}
      >
        Add phrase
      </button>
    </div>
  );
}

export function SpoilerEditor({
  spoilers,
  onChange,
}: {
  spoilers: HardSpoiler[];
  onChange: (next: HardSpoiler[]) => void;
}) {
  const replace = (index: number, spoiler: HardSpoiler) => {
    const next = [...spoilers];
    next[index] = spoiler;
    onChange(next);
  };

  return (
    <div className="af">
      <span className="af__label">Hard spoilers</span>
      <span className="af__hint">
        Only for something with a plot. The one fact a summary cannot give you &mdash; Mr.
        Robot is Elliot, Reiner is the Armored Titan. Leave it empty rather than guess:
        a wrong reveal gets somebody caught worse than no reveal.
      </span>
      {spoilers.map((spoiler, index) => (
        <div className="af__crib" key={index}>
          <div className="af__row">
            <input
              className="af__input"
              value={spoiler.reveal}
              placeholder="The reveal, stated flat"
              onChange={(event) => replace(index, { ...spoiler, reveal: event.target.value })}
            />
            <button
              type="button"
              className="af__drop"
              aria-label={`Remove spoiler ${index + 1}`}
              onClick={() => onChange(spoilers.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
          <input
            className="af__input"
            value={spoiler.lands_because}
            placeholder="Why holding this proves you watched it"
            onChange={(event) =>
              replace(index, { ...spoiler, lands_because: event.target.value })
            }
          />
          <input
            className="af__input"
            value={spoiler.where ?? ""}
            placeholder="Optional: how far in it happens"
            onChange={(event) =>
              replace(index, { ...spoiler, where: event.target.value || null })
            }
          />
        </div>
      ))}
      <button
        type="button"
        className="af__add"
        onClick={() => onChange([...spoilers, { reveal: "", lands_because: "", where: null }])}
      >
        Add a spoiler
      </button>
    </div>
  );
}
