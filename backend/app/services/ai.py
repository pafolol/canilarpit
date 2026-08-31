"""Guide generation.

One topic in, one complete reviewable `GuideDocument` out. The model never writes
straight to the catalog: everything it produces lands as a draft revision that an
editor reads and an admin publishes.

The provider is any OpenAI-compatible chat completions endpoint. We ask for a JSON
object rather than a strict schema because the guide document is a discriminated
union with length and pattern constraints that strict mode does not accept; instead
we validate with Pydantic and hand the model its own validation errors to repair.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.db.models import EntryType, GuideType
from app.schemas.content import GuideDocument, ImageQuery
from app.services import images
from app.services.text import slugify

CompletionFn = Callable[[list[dict[str, str]]], "Completion"]


class AiUnavailable(RuntimeError):
    """No provider credentials, or the provider refused the call."""


class AiGenerationFailed(RuntimeError):
    """The provider answered, but never with a document that validates."""


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class GenerationResult:
    document: GuideDocument
    warnings: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1

    @property
    def estimated_cost_micros(self) -> int:
        """Micro-units of USD, so a fraction of a cent still shows up in the audit."""
        dollars = (
            self.input_tokens * settings.openai_input_usd_per_million
            + self.output_tokens * settings.openai_output_usd_per_million
        ) / 1_000_000
        return int(round(dollars * 1_000_000))


SYSTEM_PROMPT = """\
You write for canilarpit, a reference site with exactly one question per entry: can \
you LARP this, and for how long before someone catches you?

To LARP something is to present yourself as knowing or being something you do not. \
The reader wants to hold a conversation about a film they have not watched, a scene \
they do not belong to, or a job they do not do. Your guide is the briefing they read \
beforehand.

House rules, in order of importance:

1. Be accurate. Everything factual must be true. A guide that teaches someone a wrong \
   detail gets them caught faster than saying nothing.
2. Be honest about the ceiling. Most LARPs fail, and the useful part of the guide is \
   knowing exactly where. Name the specific question, follow-up, or situation that \
   collapses it.
3. Assume it can be larped. That is what the reader came for. Almost every subject - a \
   craft, a science, a scene, a job title, a body of work, a technical field like \
   hacking or medicine or law taken as a subject of conversation - has a surface layer \
   somebody can hold, and your job is to hand it over. Reach for "dont" only when \
   making the claim would put a person at risk or take their money: presenting yourself \
   as the clinician treating someone, the lawyer filing for them, the engineer signing \
   off the building, or claiming a credential to get hired or paid. Talking \
   knowledgeably about medicine at dinner is not that. When you do write a "dont" there \
   is no crib sheet worth writing: the entry exists to say so, and the cost section is \
   the whole point of it.
4. Write flat, specific, declarative prose. No hype, no listicle voice, no "dive into", \
   no exclamation marks, no second-person cheerleading. Short sentences. Concrete nouns. \
   A named producer beats an adjective. British spelling.
5. Never invent a source. Only include a source when you are confident the page exists \
   at that URL. An empty sources list is better than a fabricated one.

The clock is the site's signature. `exposure_seconds` is your honest estimate of how \
long a motivated, knowledgeable person needs to talk to the reader before the LARP \
comes apart. Six minutes of conversation is 360. If nothing about the claim is \
checkable at all - taste in films, an opinion nobody can audit - set `unfalsifiable` \
to true and leave `exposure_seconds` null. A "dont" verdict always has \
`exposure_seconds` null and `unfalsifiable` false.

Verdicts. Three of the four mean yes, and they are meant to sound like it:

- "yes": holds indefinitely, or nobody can check, or the stakes are nil.
- "kinda": holds at the bar and fails at the table. The most common answer.
- "talk_only": the conversation holds; the doing does not. Use this whenever the \
  subject has a performable part the reader cannot perform - playing the instrument, \
  climbing the wall, popping the shell, producing the number. It is not a refusal and \
  must never read as one. Say how far the talk carries, then name the moment somebody \
  hands you the guitar. Most technical fields land here. Lead every section with
  what works before naming what does not.
- "dont": making the claim endangers somebody or defrauds them. Rare, and it should be.

Filing a subject under "dont" because it is merely difficult, technical, or easy to \
check is the one mistake that makes this site useless. Difficult is "talk_only". \
Checkable is "kinda". Dangerous is "dont".

You reply with one JSON object and nothing else. No markdown fence, no commentary."""


CONTRACT = """\
Return a JSON object with exactly these top-level keys:

{
  "schema_version": 1,
  "slug": "<kebab-case, 2-160 chars, derived from the title>",
  "title": "<display name, 2-200 chars>",
  "summary": "<10-1000 chars, one or two sentences, what this entry covers>",
  "guide_type": "<anime | screen | lifestyle | person | craft | profession | general>",
  "category_slug": "<one of: %(categories)s>",
  "aliases": ["<other names people search for; may be empty>"],
  "content": { ... see below ... },
  "sources": [
    {
      "key": "<lowercase-kebab id referenced by citations>",
      "title": "<page title>",
      "url": "https://...",
      "publisher": "<publisher or site name, optional>",
      "excerpt": null,
      "published_at": null,
      "verified_at": null
    }
  ],
  "last_verified_at": null
}

`content.kind` must equal `guide_type`. Every string inside `citations` must match a
`key` in `sources`; if you list no sources, every `citations` array must be empty.

content, for all kinds:

{
  "kind": "<same value as guide_type>",
  "larp": {
    "entry_type": "<scene | taste | role>",
    "verdict": "<yes | kinda | talk_only | dont>",
    "exposure_seconds": <integer >= 30, or null>,
    "unfalsifiable": <true only when nothing is checkable; then exposure_seconds is null>,
    "flags": ["2 or 3 SHORT UPPERCASE WARNINGS, e.g. HIGH VOCAB, SMALL SCENE,
               THEY WANT TO TEACH YOU"],
    "dek": "<10-400 chars, one sentence. Lead with what the reader CAN hold, then
             name the limit. Never open on the failure: 'You can run the whole
             vocabulary; the trouble starts when someone hands you a terminal'
             is right, 'You will be exposed as soon as anyone asks' is not.>",
    "crib": [
      {
        "heading": "References",
        "lines": ["<one fact per line, 3-6 lines, the names a real participant would say>"]
      },
      {
        "heading": "Opinions to hold",
        "lines": ["<3-5 lines, stances that read as lived rather than researched>"]
      }
    ],
    "phrases": [
      {
        "line": "<a sentence the reader says out loud, verbatim>",
        "when": "<the moment to use it>",
        "invites": "<optional: the follow-up it opens you up to>"
      }
    ],
    "surface": ["<1-3 paragraphs: what passes on first contact, and for how long>"],
    "follow_up": {
      "question": "<the exact question that ends it, in quotes>",
      "why": "<1-2 paragraphs on why that question works>",
      "counter": {
        "move": "<what the reader actually says or does when it lands. Concrete
                  and speakable: give them the sentence, not the strategy.>",
        "holds": "<how far the counter carries, and the situation it does not
                   survive. Be honest; a counter that is oversold gets somebody
                   caught worse than no counter at all.>"
      }
    },
    "tells": ["<4-6 items. Each contrasts what a larper does with what a real one does>"],
    "cost": ["<1-3 paragraphs: what actually happens when you are caught>"],
    "learn": {
      "hours": <integer: honest hours to stop pretending and just know it>,
      "book": "<one book, or 'Nothing. <the alternative>'>",
      "make": "<one concrete thing to do or make that ends the pretending>"
    }
  },
  "image_brief": [
    {
      "provider": "<one of: %(providers)s>",
      "query": "<exactly what to type into that provider's search>",
      "subject": "<what the picture is of, for the caption>",
      "role": "<hero, or the section the picture illustrates>",
      "note": "<optional: why this picture>"
    }
  ],
  "overview": "<2-4 paragraphs of background the reader needs>",
  "quick_brief": ["<4-8 one-sentence facts: the minimum not to embarrass yourself>"],
  "essential_facts": [{"fact": "<verifiable detail>", "citations": []}],
  "talking_points": [{"opener": "<something to say>",
                      "follow_up": "<where it goes next>", "context": null}],
  "vocabulary": [{"term": "<insider word>", "meaning": "<meaning>", "example": null}],
  "common_mistakes": ["<what gives newcomers away>"],
  "questions": [{"question": "<what you will be asked>", "answer": "<how to answer>"}],
  "extra_sections": [],
  "spoiler_warning": <true when the guide reveals plot>
}

The template carries its own fields on top of those. Pick it by what the subject
IS, because that decides what the reader needs:

anime - anime and manga.
  "premise", "ending_summary", "characters" (at least one, with
  {"name", "role", "fate", "relationships"}), "major_events" ({"title",
  "description", "spoiler_level": "low"|"medium"|"major", "citations"}),
  "fandom_debates" (strings).

screen - films and live-action series. Anything with an ending people argue about.
  "premise", "ending_summary", "characters", "major_events" as above, and
  "where_it_dips" (strings): the weak season, the bad sequel, the stretch
  everybody skips. Knowing where something sags is proof of attendance.

lifestyle - a scene with objects, places and a look.
  "aesthetic", "brands" ({"name", "significance", "typical_price", "citations"}),
  "visual_cues", "locations" (strings), "media_scenarios" ({"title",
  "description", "search_terms", "generation_prompt": null}).

person - a named individual whose work people claim to know: a director, a
  theorist, a novelist, a musician.
  "who": one or two paragraphs on who they are and why they come up.
  "works" ({"title", "year", "why"}): what people cite, and what each is for.
  "eras" (strings): the phases, because saying which one you prefer is how this
  is actually discussed. "positions": what they actually argue, as opposed to
  what they are assumed to. "misattributions": the quote they never said, the
  work they disowned, the position everybody assigns them and they rejected.
  That last field does more work than the bibliography; lead with it if you have
  a good one.

craft - a practised skill somebody can hand you the equipment for: baking,
  climbing, brewing, welding, picking locks.
  "proof_of_work": what a practitioner can show that a reader cannot fake.
  "tools" ({"name", "why", "typical_price"}), "techniques" (the words for what
  the hands do), "failure_modes" (how it goes wrong, named the way somebody who
  has done it would name them).

profession - a job title.
  "day_to_day": what the work actually consists of, which is duller than the
  claim and that is the useful part. "red_lines" (at least one): where claiming
  this stops being a social bluff and becomes fraud or danger - an interview,
  taking money, somebody relying on it. Every profession guide states these
  whatever its verdict. "hierarchy" (the titles people are touchy about),
  "credentials" ({"name", "what_it_takes"}).

general - everything with no better home.
  "key_people" and "timeline" (strings).

`image_brief` is 4 to 6 pictures, spread through the article rather than piled at
the top. Exactly one carries `role: "hero"`. Give the others the section they
illustrate, so a reader meets a picture beside the point it belongs to:

  crib      the references and names the guide tells you to drop
  surface   what passes on first contact
  tells     what a real participant does that you would not
  cost      what being caught looks like
  learn     the honest alternative: the place, the tool, the practice
  gallery   no strong opinion; it lands at the end

Choosing the right provider matters more than the wording of the query:

%(provider_help)s

Name the actual thing. For a film, series or anime, the query is the title, or a
character's name, not a description of a mood. For anything physical - a drink, a
loaf, a building, a piece of clothing - the query is a plain description of the
photograph you want. Never send a fictional character to a stock photography
provider: it has never heard of them and will return a stranger.

`phrases` is 3 to 5 lines the reader can say, and it is not the crib sheet in
another form. The crib is what to know; a phrase is a sentence with the shape
somebody who belongs would use, and it has to survive being said out loud by
somebody who is bluffing.

The good ones are short, specific, and safe to be asked about - "It's a tyre race
now", "What's the roast date?", "I can't talk about live numbers", "Who is Rem?".
The bad ones are facts in disguise, anything that invites a question the reader
cannot answer, and anything nobody would actually say. When a line does invite a
dangerous follow-up but is worth it anyway, put the follow-up in `invites` and
say how to survive it.

A "dont" entry has `phrases: []`. It hands out no lines.

Query one thing. "Breaking Bad" finds the show, "Walter White" finds the
character; "Breaking Bad Walter White fsociety mood" finds neither. A subject
per entry.

Use "auto" only when you genuinely cannot tell.

The counter is the part of the guide that does the most work, so write it last
and write it hardest. The reader is standing in the conversation when the
question lands, and a strategy is no use to them: hand them the words. The best
counters are usually one of four moves - answer honestly because honesty is
unanswerable here, hand the question back because the room would rather teach
than test, change the axis to something you do know, or decline on a ground the
room accepts. Say which situation it fails in.

Set `counter` to null only when there genuinely is not one. A "dont" entry must
have `counter: null`: the answer to that question is not to have claimed it.

A "dont" entry still needs every field. Write `crib` as a single section headed
"Why this one is different" explaining what the claim actually costs other people,
keep `surface` short, and put the real weight in `cost`."""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def chat_completion(messages: list[dict[str, str]]) -> Completion:
    if not settings.ai_configured:
        raise AiUnavailable("OPENAI_API_KEY is not configured")

    payload: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
    }
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    try:
        response = httpx.post(
            url,
            headers=_headers(),
            json=payload,
            timeout=settings.openai_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise AiUnavailable(f"Could not reach the model provider: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        raise AiUnavailable(f"Model provider returned {response.status_code}: {detail}")

    body = response.json()
    try:
        text = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AiGenerationFailed("Model provider returned an unreadable response") from exc
    usage = body.get("usage") or {}
    return Completion(
        text=text,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -len("```")]
    return cleaned.strip()


def _format_errors(error: ValidationError) -> str:
    lines = []
    for item in error.errors()[:20]:
        location = ".".join(str(part) for part in item["loc"])
        lines.append(f"- {location}: {item['msg']}")
    return "\n".join(lines)


def build_prompt(
    topic: str,
    *,
    category_slugs: Sequence[str],
    guide_type: GuideType | None,
    entry_type: EntryType | None,
    instructions: str | None,
) -> list[dict[str, str]]:
    request = [f'Write the canilarpit entry for: "{topic}".']
    if guide_type:
        request.append(f'Use guide_type "{guide_type.value}".')
    else:
        request.append(
            "Choose guide_type yourself, by what the subject is: anime for anime and "
            "manga, screen for films and live-action series, lifestyle for a scene "
            "with objects and a look, person for a named individual whose work "
            "people claim to know, craft for a practised skill somebody could "
            "hand you the equipment for, profession for a job title, general only "
            "when none of those fit."
        )
    if entry_type:
        request.append(f'Use larp.entry_type "{entry_type.value}".')
    if instructions:
        request.append(f"Editor instructions, which override the defaults:\n{instructions}")

    contract = CONTRACT % {
        "categories": ", ".join(category_slugs),
        "providers": ", ".join(provider.id for provider in images.PROVIDERS.values()),
        "provider_help": provider_guidance(),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(request) + "\n\n" + contract},
    ]


def coerce_document(raw: str, *, topic: str) -> GuideDocument:
    payload = json.loads(_strip_fence(raw))
    if not isinstance(payload, dict):
        raise ValueError("the model did not return a JSON object")
    payload.setdefault("schema_version", 1)
    payload.setdefault("title", topic)
    if not payload.get("slug"):
        payload["slug"] = slugify(str(payload.get("title") or topic))
    return GuideDocument.model_validate(payload)


def generate_guide_document(
    topic: str,
    *,
    category_slugs: Sequence[str],
    guide_type: GuideType | None = None,
    entry_type: EntryType | None = None,
    instructions: str | None = None,
    complete: CompletionFn | None = None,
) -> GenerationResult:
    """Ask for a guide, and hand back validation errors until it is a valid document."""
    call = complete or chat_completion
    messages = build_prompt(
        topic,
        category_slugs=category_slugs,
        guide_type=guide_type,
        entry_type=entry_type,
        instructions=instructions,
    )

    input_tokens = 0
    output_tokens = 0
    last_error = ""
    for attempt in range(1, settings.ai_max_repair_attempts + 2):
        completion = call(messages)
        input_tokens += completion.input_tokens
        output_tokens += completion.output_tokens
        try:
            document = coerce_document(completion.text, topic=topic)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = (
                _format_errors(exc) if isinstance(exc, ValidationError) else str(exc)
            )
            messages = messages + [
                {"role": "assistant", "content": completion.text[:20000]},
                {
                    "role": "user",
                    "content": (
                        "That document did not validate. Fix exactly these problems and "
                        "return the complete corrected JSON object, not a patch:\n"
                        f"{last_error}"
                    ),
                },
            ]
            continue

        return GenerationResult(
            document=document,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            attempts=attempt,
        )

    raise AiGenerationFailed(
        f"The model could not produce a valid guide document. Last errors:\n{last_error}"
    )


def verify_sources(
    document: GuideDocument, *, timeout: float = 6.0
) -> tuple[GuideDocument, list[str]]:
    """Drop sources whose URL does not resolve, and the citations that pointed at them.

    A generated citation is worthless if the page is not there, and a dead link in a
    published guide is worse than no link at all.
    """
    if not document.sources:
        return document, []

    payload = document.model_dump(mode="json", exclude_none=False)
    alive: list[dict[str, Any]] = []
    dropped: list[str] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for source in payload.get("sources") or []:
            url = source.get("url")
            try:
                response = client.head(url)
                if response.status_code >= 400:
                    response = client.get(url)
                ok = response.status_code < 400
            except httpx.HTTPError:
                ok = False
            if ok:
                alive.append(source)
            else:
                dropped.append(source["key"])

    if not dropped:
        return document, []

    payload["sources"] = alive
    _strip_citations(payload.get("content") or {}, set(dropped))
    warning = (
        f"Dropped {len(dropped)} source(s) whose URL did not resolve: {', '.join(dropped)}"
    )
    return GuideDocument.model_validate(payload), [warning]


def _strip_citations(node: Any, dropped: set[str]) -> None:
    if isinstance(node, dict):
        citations = node.get("citations")
        if isinstance(citations, list):
            node["citations"] = [key for key in citations if key not in dropped]
        for value in node.values():
            _strip_citations(value, dropped)
    elif isinstance(node, list):
        for value in node:
            _strip_citations(value, dropped)


def provider_guidance() -> str:
    """The registry, rendered for the prompt, so the two can never drift apart."""
    lines = ["- auto: let the backend choose from the category. A last resort."]
    for provider in images.PROVIDERS.values():
        lines.append(f"- {provider.id}: {provider.subjects}")
    return "\n".join(lines)


def image_plan(document: GuideDocument, *, limit: int = 6) -> list[ImageQuery]:
    """What to fetch, in order. The model's brief wins; otherwise we infer one."""
    brief = list(document.content.image_brief)
    if not brief:
        brief = inferred_brief(document)

    seen: set[str] = set()
    plan: list[ImageQuery] = []
    for item in brief:
        key = f"{item.provider}:{item.query.lower()}"
        if key in seen:
            continue
        seen.add(key)
        plan.append(item)
        if len(plan) >= limit:
            break
    if plan:
        plan[0] = plan[0].model_copy(update={"role": "hero"})
    return plan


def inferred_brief(document: GuideDocument) -> list[ImageQuery]:
    """A brief for documents written before image_brief existed."""
    content = document.content
    queries: list[ImageQuery] = []

    for scenario in getattr(content, "media_scenarios", []):
        for term in scenario.search_terms:
            queries.append(ImageQuery(query=term, subject=scenario.title))
    for cue in getattr(content, "visual_cues", [])[:3]:
        queries.append(ImageQuery(query=cue, subject=document.title))
    queries.append(ImageQuery(query=document.title, subject=document.title))
    return queries


SCREEN_PROMPT = """\
You are triaging a reader's suggestion for canilarpit before an editor spends \
time on it. Answer with one JSON object and nothing else:

{
  "verdict": "<accept | reject | spam>",
  "reason": "<one sentence an editor reads, and which may be shown to the sender>",
  "guide_type": "<the content template. Exactly one of: %(types)s. Null if unsure.
                  This is not the category; do not answer with a category here.>",
  "entry_type": "<scene | taste | role, or null>",
  "category_slug": "<the subject area. Exactly one of: %(categories)s. Null if unsure.>",
  "concerns": ["<anything an editor should know before publishing>"]
}

"accept" means this is a real subject somebody could plausibly want to bluff \
about, and there is enough here to write from. Be generous: a thin suggestion \
about a real thing is still work worth doing, and the note only has to show the \
sender means it.

"reject" means the subject is not something anybody could larp, the note is \
empty of content, or the site already covers it. Say which.

"spam" means advertising, abuse, gibberish, or an attempt to use the form as a \
channel for something else.

Reject, and say so in `concerns`, when the subject is a private individual \
rather than a public figure or a public body of work. A guide about how to \
impersonate somebody's neighbour is not what this site is. The same goes for \
anything whose point is to defraud or endanger a named person."""


def screen_submission(
    topic: str,
    notes: str,
    *,
    category_slugs: Sequence[str],
    credit: str | None = None,
    complete: CompletionFn | None = None,
) -> dict[str, Any]:
    """Triage one submission. Cheap, and it runs before anything expensive."""
    call = complete or chat_completion
    system = SCREEN_PROMPT % {
        "types": " | ".join(guide_type.value for guide_type in GuideType),
        "categories": ", ".join(category_slugs),
    }
    submission = f"Topic: {topic}\n\nWhat the sender says they know:\n{notes}"
    if credit:
        submission += f"\n\nThey asked to be credited as: {credit}"

    completion = call(
        [{"role": "system", "content": system}, {"role": "user", "content": submission}]
    )
    try:
        payload = json.loads(_strip_fence(completion.text))
    except json.JSONDecodeError as exc:
        raise AiGenerationFailed("The screening reply was not JSON") from exc
    if not isinstance(payload, dict) or payload.get("verdict") not in {
        "accept",
        "reject",
        "spam",
    }:
        raise AiGenerationFailed("The screening reply had no usable verdict")

    payload["input_tokens"] = completion.input_tokens
    payload["output_tokens"] = completion.output_tokens
    return payload
