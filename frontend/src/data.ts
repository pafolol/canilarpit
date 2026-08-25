export type Verdict = "YES" | "KINDA" | "NOT REALLY" | "DON'T";
export type EntryType = "scene" | "taste" | "role";

/** seconds, "indefinite" for unfalsifiable, null for ⛔️ entries (no clock runs) */
export type Clock = number | "indefinite" | null;

export type CribSection = { heading: string; lines: string[] };

export type Entry = {
  slug: string;
  name: string;
  type: EntryType;
  category: string;
  verdict: Verdict;
  clock: Clock;
  flags: string[];
  dek: string;
  crib: CribSection[];
  surface: string[];
  followUp: string[];
  tells: string[];
  cost: string[];
  learn: { hours: number; book: string; make: string };
};

export const VERDICTS: Verdict[] = ["YES", "KINDA", "NOT REALLY", "DON'T"];
export const TYPES: EntryType[] = ["scene", "taste", "role"];
export const TYPE_GLYPH: Record<EntryType, string> = { scene: "◆", taste: "●", role: "▲" };

export const entries: Entry[] = [
  {
    slug: "natural-wine",
    name: "Natural wine",
    type: "taste",
    category: "drink",
    verdict: "KINDA",
    clock: 360,
    flags: ["HIGH VOCAB", "SMALL SCENE", "THEY WANT TO TEACH YOU"],
    dek: "The scene is welcoming and the canon is public. You pass at the bar and fail at the table.",
    crib: [
      {
        heading: "References",
        lines: [
          "Gravner. Amphora, oxidative, orange.",
          "Overnoy. Jura, Poulsard, the text everyone starts from.",
          "Frank Cornelissen. Etna. Volcanic and divisive.",
          "Alice Feiring and Pipette are where the language comes from.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "Some of it is faulty. Say so.",
          "Sulfites are not the villain. Dose is.",
          "Pét-nat is a starting point, not a destination.",
          "You like the ones that still taste like grapes.",
        ],
      },
    ],
    surface: [
      "A producer, a region, and one flaw. Three items is the entire surface layer, and it holds for about six minutes.",
      "Order by the glass and ask what was opened today. Curiosity outranks knowledge in this room, which is why the bar is survivable and the table is not.",
    ],
    followUp: [
      "\"What did you think of the last vintage?\"",
      "Vintage variation is the trapdoor. Natural wine moves year to year more than anything else on the list, so a person who has been drinking it has an opinion about 2021 and a person who has been reading about it has a producer name and nothing after it.",
    ],
    tells: [
      "You call it natural wine. They say the producer.",
      "You praise funk in general. Funk is not a flavour to them, it is a defect they have decided to forgive in three specific bottles.",
      "You cannot say where you drank it. Bottles come from places and the place is half the story.",
      "You say it is alive. Everyone says it is alive. Nobody says it about a bottle they actually finished.",
    ],
    cost: [
      "Low. This scene forgives ignorance and punishes confidence.",
      "Ask instead of assert and the clock stops running. That is not a trick, it is how the room works.",
    ],
    learn: {
      hours: 20,
      book: "The Dirty Guide to Wine — Alice Feiring",
      make: "Drink twelve bottles from six producers. Write one line each.",
    },
  },
  {
    slug: "letterboxd",
    name: "Letterboxd",
    type: "taste",
    category: "film",
    verdict: "YES",
    clock: "indefinite",
    flags: ["PUBLIC CANON", "NO GATEKEEPER", "LOW STAKES"],
    dek: "The canon is public, the reviews are free, and nobody can audit whether you watched it.",
    crib: [
      {
        heading: "References",
        lines: [
          "Jeanne Dielman. The 2022 Sight & Sound number one.",
          "Tsai Ming-liang. Long takes, little dialogue.",
          "Wong Kar-wai. Everyone has seen it, few have rewatched it.",
          "Four and a half is the ceiling. Five is a personality statement.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "The letterboxing joke is old and you are past it.",
          "You log rewatches, which is the mark of an account in use.",
          "Any director's consensus favourite is their third best.",
        ],
      },
    ],
    surface: [
      "A list, a rating, and one sentence. The one sentence is the platform's whole register.",
      "Never write a paragraph. The form is a caption and length reads as effort, which reads as new.",
    ],
    followUp: [
      "\"What have you actually watched this month?\"",
      "Larpers have a canon. Users have a recent history, and a real one is full of mediocre films watched on a Tuesday for no reason.",
    ],
    tells: [
      "Every favourite is above four stars. Real accounts have a two-star film they will defend at length.",
      "No rewatches. Nobody who loves film watches everything exactly once.",
      "You talk about films. Users talk about watching films, which is a different subject with different sentences.",
    ],
    cost: [
      "None. There is no one to catch you, and that is the finding rather than an oversight.",
      "The only exposure is to yourself, eventually, in a conversation with someone who has seen it.",
    ],
    learn: {
      hours: 6,
      book: "Nothing. Watch four films.",
      make: "Log twenty films you have already seen, honestly, including the bad ones.",
    },
  },
  {
    slug: "prestige-tv",
    name: "Prestige TV",
    type: "taste",
    category: "series",
    verdict: "KINDA",
    clock: 300,
    flags: ["SMALL CANON", "NO GATEKEEPER", "SPOILER RISK"],
    dek: "The canon is small and the opinions are borrowed from the same four essays. You pass until somebody names a season.",
    crib: [
      {
        heading: "References",
        lines: [
          "The Sopranos, The Wire, Mad Men. The three-name spine.",
          "Season two is the contested one, in almost every show.",
          "The Wire season four is the correct answer and saying it marks you as ordinary.",
          "Prestige is a budget and a runtime before it is a quality.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "The finale discourse is more interesting than the finales.",
          "Six episodes is not a season.",
          "Every show got worse once it knew it was prestige.",
        ],
      },
    ],
    surface: [
      "A show, a season, and a supporting character. Nobody checks the first two.",
      "Everyone has seen the pilot of everything. Nothing above episode four is safe.",
    ],
    followUp: [
      "\"Which season?\"",
      "It is the only question in the form and it gets asked constantly, because seasons are how people who actually watched store the show.",
    ],
    tells: [
      "You quote the famous line. Everyone has the famous line, it was in the trailer.",
      "You talk about the writing. Viewers talk about one scene.",
      "You have no show you gave up on. Everyone has one and it is usually season three.",
    ],
    cost: [
      "None worth counting. This is the lowest-stakes claim on the site.",
      "Somebody will spoil something for you, which is the only enforcement this scene has.",
    ],
    learn: {
      hours: 60,
      book: "Difficult Men \u2014 Brett Martin",
      make: "Finish one show you abandoned.",
    },
  },
  {
    slug: "quant",
    name: "Quant",
    type: "role",
    category: "job",
    verdict: "DON'T",
    clock: null,
    flags: ["MATH IS CHECKABLE", "NDA CULTURE", "ONE QUESTION ENDS IT"],
    dek: "The claim is falsifiable in one question and the answer is a number. There is no surface layer here, only a surface.",
    crib: [],
    surface: [],
    followUp: [
      "\"What's your Sharpe?\"",
      "It is small talk to them. It is a number, you do not have one, and there is no version of not answering that reads as anything other than not having one.",
    ],
    tells: [
      "You describe strategies. They describe constraints, because the constraints are the job.",
      "You say alpha. Nobody says alpha.",
      "You cannot say what broke. Everyone in the seat has one thing that broke and cost them a quarter, and they will tell you about it unprompted.",
    ],
    cost: [
      "Immediate and total. This is one of the few claims that can be falsified at the table, in under a minute, by someone who is only being friendly.",
      "The failure is not social. Anyone in the room who is actually in the field now knows you lied about your job, and they work in an industry that keeps a list and is small enough for the list to matter.",
      "If money moved on the claim, it stops being a social matter.",
    ],
    learn: {
      hours: 2000,
      book: "Advances in Financial Machine Learning — Marcos López de Prado",
      make: "A backtest that loses money honestly.",
    },
  },
  {
    slug: "techno",
    name: "Techno",
    type: "scene",
    category: "music",
    verdict: "KINDA",
    clock: 240,
    flags: ["RITUAL OVER TASTE", "TIME-BASED", "SMALL SCENE"],
    dek: "The music is easy and the ritual is not. You pass in conversation and fail at four in the morning.",
    crib: [
      {
        heading: "References",
        lines: [
          "Basic Channel and Chain Reaction. The dub techno lineage.",
          "Jeff Mills, Robert Hood. Detroit minimalism.",
          "Ostgut Ton as a label, not as a building.",
          "Giegling and Perlon for the softer end of the argument.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "The room and the hour matter more than the lineup.",
          "Most of it is boring, and boring is the compliment.",
          "A set is judged at hour four, not at the peak.",
        ],
      },
    ],
    surface: [
      "Rooms and hours, not tracks. Nobody in this scene identifies music on their phone and nobody admits to wanting to.",
      "The correct answer to what was played is a mood and a time.",
    ],
    followUp: [
      "\"What time did you get there?\"",
      "Arrival time is the entire class system of this scene, it is asked casually, and there is no way to guess the right answer because the right answer is different in every city.",
    ],
    tells: [
      "You name DJs. They name nights.",
      "You describe the drop. There is no drop, that is a different genre, and nobody will correct you out loud.",
      "You left before three. Everything worth defending happens after three.",
      "You dressed for it. The people who belong dressed for a laundry day.",
    ],
    cost: [
      "Moderate. The scene is not cruel but it is closed, and it remembers faces better than it remembers names.",
      "You will not be told. You will simply stop being included in the message.",
    ],
    learn: {
      hours: 60,
      book: "Energy Flash — Simon Reynolds",
      make: "Stay until close, once, sober.",
    },
  },
  {
    slug: "specialty-coffee",
    name: "Specialty coffee",
    type: "taste",
    category: "drink",
    verdict: "YES",
    clock: 900,
    flags: ["THEY WANT TO TEACH YOU", "PUBLIC CANON", "LOW STAKES"],
    dek: "Fifteen minutes of vocabulary buys you a year. The scene is evangelical and wants you inside it.",
    crib: [
      {
        heading: "References",
        lines: [
          "Washed against natural. This one distinction does most of the work.",
          "Gesha as the expensive varietal. Bourbon and Typica as the floor.",
          "Ethiopia for florals, Colombia for balance, Kenya for acidity.",
          "James Hoffmann is the shared reference and nobody is embarrassed about it.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "Light roast is not better, it is more legible.",
          "Grind matters more than the machine.",
          "Most third wave cafés under-extract to look current.",
        ],
      },
    ],
    surface: [
      "Order a filter, ask what is on, ask about the process. Three moves and you are inside the conversation.",
      "Say what you taste even when you are wrong. Being wrong out loud is the accepted entry ritual here, which is why the clock runs so long.",
    ],
    followUp: [
      "\"How do you make it at home?\"",
      "There is no bluff available. Either there is a grinder on your counter or there is not, and the follow-up to the answer is what grinder.",
    ],
    tells: [
      "You praise the beans. They talk about the roast, the water, and the grinder, in that order.",
      "You say notes of, and then read the bag out loud.",
      "You have opinions about origin and none about water. Water is half of it.",
    ],
    cost: [
      "Very low. The worst outcome is a barista explaining something to you for eleven minutes.",
      "Nobody in this scene has ever been glad to catch someone out.",
    ],
    learn: {
      hours: 15,
      book: "The World Atlas of Coffee — James Hoffmann",
      make: "Dial in one bean on one grinder across five days.",
    },
  },
  {
    slug: "climbing",
    name: "Climbing",
    type: "scene",
    category: "sport",
    verdict: "NOT REALLY",
    clock: 180,
    flags: ["PHYSICALLY CHECKABLE", "GRADED", "SMALL SCENE"],
    dek: "The scene is physical and the grade is public. Your body is the audit and it runs in front of everyone.",
    crib: [
      {
        heading: "References",
        lines: [
          "V-scale for boulder, French or YDS for rope. Know which the room uses.",
          "Fontainebleau, Hueco, Céüse as the named places.",
          "Beta is the sequence. Flash, onsight and project are three different things.",
          "Ondra and Sharma are the household names, which is itself a tell.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "Grades are soft everywhere except at your own gym.",
          "Projecting one problem beats volume.",
          "Indoor and outdoor are different sports.",
        ],
      },
    ],
    surface: [
      "Vocabulary lasts about three minutes. Then somebody suggests you get on the wall, and the suggestion is friendly.",
      "There is no version of this scene that stays verbal.",
    ],
    followUp: [
      "\"Want to jump on this one?\"",
      "It is an invitation rather than a test, which is exactly why it is fatal. You can decline once. You cannot decline twice.",
    ],
    tells: [
      "Your hands are wrong. Nobody who climbs has those hands.",
      "You know the numbers but not the movement, and you describe routes by grade instead of by what they ask of you.",
      "You say you climb but not where. Every climber has a home wall and names it in the first sentence.",
    ],
    cost: [
      "Low socially, high in the moment. Nobody is angry and everybody saw it.",
      "The scene is small enough that the story travels to the next gym before you do.",
    ],
    learn: {
      hours: 120,
      book: "The Rock Warrior's Way — Arno Ilgner",
      make: "Twelve sessions. Nothing substitutes for the sessions.",
    },
  },
  {
    slug: "anaesthetist",
    name: "Anaesthetist",
    type: "role",
    category: "job",
    verdict: "DON'T",
    clock: null,
    flags: ["DUTY IMPLIED", "ONE QUESTION ENDS IT", "LEGAL EXPOSURE"],
    dek: "Do not. The claim carries duty implications that outlive the dinner party.",
    crib: [],
    surface: [],
    followUp: [
      "\"What do you use for induction?\"",
      "There is a small, boring, universally known answer, and every actual anaesthetist gives it without thinking about it first. The pause is the whole tell.",
    ],
    tells: [
      "You talk about surgery. They talk about the twenty minutes before and the twenty minutes after, because that is the job.",
      "You describe drama. The profession is the management of boredom punctuated by four minutes.",
      "You have no opinion about the coffee in that hospital. Everyone has one.",
    ],
    cost: [
      "This is the entry that changes category. Claiming a clinical role is not a social bluff, and in most places it stops being only a social matter the moment anyone acts on it.",
      "The room contains a nurse more often than you expect.",
      "If somebody collapses at that dinner, the claim becomes the only fact anyone remembers about you.",
    ],
    learn: {
      hours: 20000,
      book: "Miller's Anesthesia",
      make: "Medical school. There is no shorter path and that is the point.",
    },
  },
  {
    slug: "brutalism",
    name: "Brutalism",
    type: "taste",
    category: "design",
    verdict: "KINDA",
    clock: 300,
    flags: ["HIGH VOCAB", "IMAGE-LED", "THEY WANT TO TEACH YOU"],
    dek: "Everyone has the images and nobody has the buildings. You pass on a screen and fail on the street.",
    crib: [
      {
        heading: "References",
        lines: [
          "Béton brut. The term is about the concrete, not the mood.",
          "Le Corbusier, Unité d'Habitation. The origin point.",
          "Goldfinger's Trellick Tower. Lasdun's National Theatre.",
          "Reyner Banham named it and then complained about what it became.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "It was social housing before it was an aesthetic.",
          "Most of what gets posted is not brutalism, it is just concrete.",
          "The demolitions are the actual subject.",
        ],
      },
    ],
    surface: [
      "A building, its architect, and what it was built for. The third item is where larpers stop.",
      "Photographs carry you a long way here, which is why the clock is generous and the failure is specific.",
    ],
    followUp: [
      "\"Have you been inside one?\"",
      "The interiors are the argument. Every photograph in circulation is an exterior, so the inside is the one thing no amount of scrolling supplies.",
    ],
    tells: [
      "You post exteriors. The people who care talk about corridors, light wells, and how the lifts work.",
      "You call it brutal. The word is about the concrete.",
      "You have no opinion about who lives there now, which means you are looking at a picture rather than a building.",
    ],
    cost: [
      "Low. Somebody will send you a reading list, which is this scene's version of a punishment.",
      "You will be invited to a walking tour and the walking tour is where it ends.",
    ],
    learn: {
      hours: 25,
      book: "The New Brutalism — Reyner Banham",
      make: "Visit three and walk the corridors.",
    },
  },
  {
    slug: "crypto-vc",
    name: "Crypto VC",
    type: "role",
    category: "job",
    verdict: "YES",
    clock: "indefinite",
    flags: ["UNFALSIFIABLE", "PUBLIC VOCAB", "NO GATEKEEPER"],
    dek: "Nothing here is checkable, the vocabulary is public, and the real thing fails in the same way the bluff does.",
    crib: [
      {
        heading: "References",
        lines: [
          "Thesis, allocation, liquid against locked, cliff and vest.",
          "SAFT, then SAFE plus token warrant. The paperwork moved and knowing that dates you correctly.",
          "Name a fund you are not at and a deal you did not lead.",
          "Everyone is quietly holding something from 2021 they will not mark down.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "Most of the last cycle was infrastructure with no users.",
          "Distribution is the hard part now, not the technology.",
          "You were early and you sized it wrong. Unverifiable and universally true.",
        ],
      },
    ],
    surface: [
      "Thesis, stage, check size, then decline to be specific. Declining is not evasion in this room, it is the register.",
      "The surface layer and the actual layer are the same layer. That is why the clock does not run.",
    ],
    followUp: [
      "\"What did you pass on?\"",
      "There is no follow-up that kills you. Any plausible answer holds, and nobody can check, and that is the entire finding.",
    ],
    tells: [
      "You are too specific. The real ones are vague on purpose and vague in a particular direction.",
      "You have no complaints about your LPs.",
      "You sound excited. Nobody in the seat has sounded excited since 2021.",
    ],
    cost: [
      "Low, and mostly borne by other people.",
      "The exception is money. The moment somebody wires on the strength of the claim, this entry no longer applies to you.",
    ],
    learn: {
      hours: 40,
      book: "The last eight quarterly letters from any fund",
      make: "A one-page thesis you would defend to a stranger.",
    },
  },
  {
    slug: "jazz",
    name: "Jazz",
    type: "taste",
    category: "music",
    verdict: "NOT REALLY",
    clock: 120,
    flags: ["PLAYERS PRESENT", "DEEP CANON", "TIME-BASED"],
    dek: "The canon is deep, the listening is checkable in real time, and the room usually contains a player.",
    crib: [
      {
        heading: "References",
        lines: [
          "Kind of Blue is the correct entry and the wrong answer to a favourite.",
          "Coltrane before and after 1965 are two different subjects.",
          "Mingus, Monk, Bill Evans as the safe middle.",
          "Rhythm sections. Nobody larping has ever mentioned a bass player.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "The live record is usually the better one.",
          "Fusion is not the insult it used to be.",
          "You listen to the drummer first. This is a real position and it is defensible.",
        ],
      },
    ],
    surface: [
      "One album, one player who is not the bandleader, one live recording. Two minutes in total.",
      "The surface is short here because the record is usually already playing.",
    ],
    followUp: [
      "\"Who's playing on it?\"",
      "Personnel is the language of the form and it is printed on the sleeve, so not knowing is not the kind of gap that gets forgiven.",
    ],
    tells: [
      "You name bandleaders only.",
      "You say improvisation as though the word explained something.",
      "You cannot hum a head. Everyone who listens can hum four.",
      "It is playing right now and you are still talking.",
    ],
    cost: [
      "Moderate. Someone will put on a record and stop talking to you, which is the entire punishment and it is sufficient.",
      "Nothing is said. That is worse.",
    ],
    learn: {
      hours: 80,
      book: "Thinking in Jazz — Paul Berliner",
      make: "Learn to hear the bass line on ten records.",
    },
  },
  {
    slug: "sourdough",
    name: "Sourdough",
    type: "taste",
    category: "food",
    verdict: "YES",
    clock: 600,
    flags: ["PUBLIC CANON", "THEY WANT TO TEACH YOU", "SLOW PROOF"],
    dek: "The knowledge is free, the practice is slow, and nobody is going to ask you to produce a loaf tonight.",
    crib: [
      {
        heading: "References",
        lines: [
          "Hydration as a percentage. The whole hobby is spoken in percentages.",
          "Tartine is the shared text. Forkish is the other one.",
          "Bulk ferment, shaping, cold retard. The three stages.",
          "Banneton, lame, dutch oven. The three objects.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "Starter age is a joke, not a credential.",
          "Open crumb is overrated and mostly hydration.",
          "The oven matters less than the shaping.",
        ],
      },
    ],
    surface: [
      "A hydration number, a flour, and a complaint about your oven. That is the entire first conversation and it renews.",
      "Nothing about this scene happens on a deadline, which is why the clock is long.",
    ],
    followUp: [
      "\"Can I see it?\"",
      "Everyone photographs the crumb. Having no photograph is the only real failure state, and it is recoverable within a week.",
    ],
    tells: [
      "You talk about the starter and not the schedule. The schedule is the hobby.",
      "You have no complaint. Every baker has one recurring failure they are mid-argument with.",
      "You say artisan.",
    ],
    cost: [
      "None. The worst outcome is that somebody gives you starter, which is a gift and an obligation.",
      "You will be asked about it in three weeks. That is the only follow-up.",
    ],
    learn: {
      hours: 30,
      book: "Tartine Bread — Chad Robertson",
      make: "Six loaves. The fourth is where it starts working.",
    },
  },
  {
    slug: "f1",
    name: "Formula 1",
    type: "scene",
    category: "sport",
    verdict: "YES",
    clock: "indefinite",
    flags: ["PUBLIC DATA", "LARGE SCENE", "NO GATEKEEPER"],
    dek: "The sport publishes everything. Every fact you would need is on a timing screen and half the paddock is guessing too.",
    crib: [
      {
        heading: "References",
        lines: [
          "Undercut, overcut, dirty air, degradation. Four words carry most of the analysis.",
          "Ground effect and the 2022 regulation change.",
          "Adrian Newey as the shared name for design.",
          "Any pre-2010 opinion marks you as older, which reads as credible.",
        ],
      },
      {
        heading: "Opinions to hold",
        lines: [
          "The racing got worse and the coverage got better.",
          "Strategy is more interesting than the driver market.",
          "The sprint format solves a problem nobody had.",
        ],
      },
    ],
    surface: [
      "One race, one strategy call, one complaint about stewarding. Endlessly renewable and never checked.",
      "The fandom quadrupled in four years, so being new is the statistical default rather than a mark against you.",
    ],
    followUp: [
      "\"Were you watching before Drive to Survive?\"",
      "It is a status question and the lie is checkable through a single 2017 detail. Answering honestly costs nothing, which is why the verdict holds.",
    ],
    tells: [
      "You only know current drivers.",
      "You talk about overtakes and not tyres. The sport is about tyres.",
      "You have no team you resent. Everyone has one.",
    ],
    cost: [
      "None. Everybody arrived recently and everybody knows it.",
      "The only people who mind are the ones who arrived eighteen months before you.",
    ],
    learn: {
      hours: 10,
      book: "The Mechanic — Marc Priestley",
      make: "Watch one race with the timing screen open.",
    },
  },
];

export const categories = [...new Set(entries.map((e) => e.category))].sort();

export const bySlug = (slug: string) => entries.find((e) => e.slug === slug);

export const caught = [
  {
    where: "A dinner in Lisbon, March",
    question: "So which vintage did you have?",
    after: "He had said Overnoy twice. The table waited. Four seconds is a long time.",
  },
  {
    where: "A gym in Leipzig, November",
    question: "Want to jump on this one?",
    after: "It was the warm-up. She got two moves in and came down laughing, which helped.",
  },
  {
    where: "A rooftop in Brooklyn, July",
    question: "What's your Sharpe?",
    after: "It was small talk. He answered with a range. Ranges are not answers.",
  },
];
