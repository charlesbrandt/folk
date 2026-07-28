// Types mirror web/routers/*.py's JSON shapes exactly -- see
// web/serialize.py for the tiered-index / edge-list reshaping this renders.

export interface Collection {
  name: string
  dir: string
}

export interface PersonSummary {
  slug: string
  name: string
  collection: string
}

export interface Association {
  name: string
  type: string
  ref: string | null
}

export interface MediaItem {
  ref: string
  note: string
}

// One ## Dates entry (docs/design/web-ui.md Decision 4) -- month_day is
// always zero-padded 'MM-DD', year optional.
export interface PersonDate {
  label: string
  month_day: string
  year: number | null
}

// One index record -- the exact shape journal.py's replay() writes to
// ~/.folk/triples.ndjson, plus a `staleness` field computed at read time
// (never persisted) by serialize.tiered_index_json.
export interface IndexRecord {
  s: string
  p: string
  o: string
  tier: string
  col: string
  src?: string
  note?: string
  when?: string
  locus?: string
  last_reinforced?: string
  reinforce_count?: number
  superseded_by?: string
  staleness: 'fresh' | 'aging' | 'stale'
}

export interface TierGroup {
  tier: string
  label: string
  records: IndexRecord[]
}

export interface TieredIndex {
  tiers: TierGroup[]
  superseded: IndexRecord[]
}

export interface AppearanceLabel {
  label: string
  value: string
}

export interface Appearance {
  labels: AppearanceLabel[]
  note: string
}

export interface PersonProfile {
  slug: string
  collection: string
  name: string
  file: string
  bio: string
  archetype: string
  voice: string
  appearance: Appearance
  appearance_checkpoints: Record<string, Appearance>
  tags: string[]
  associations: Association[]
  media: MediaItem[]
  dates: PersonDate[]
  defining_moments: string[]
  journal_file: string | null
  index: TieredIndex
}

export interface LocusSummary {
  slug: string
  name: string
  collection: string | null
}

export interface LocusProfile {
  slug: string
  collection: string | null
  name: string
  file: string
  genius_loci: string
  tags: string[]
  associations: Association[]
  media: MediaItem[]
  index: TieredIndex
}

export interface LocusTimeline {
  locus: string
  events: IndexRecord[]
}

export interface GraphNode {
  id: string
  label: string
}

export interface GraphEdge {
  source: string
  predicate: string
  target: string
}

export interface EdgeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// The Home dashboard's Reminders panel (docs/design/web-ui.md 2a) -- the
// exact shape folk.agenda.upcoming() returns, plus `collection` (added by
// GET /agenda so a row can link to that person's page).
export interface AgendaItem {
  date: string
  days_until: number
  label: string
  person: string
  person_id: string
  file: string
  collection: string | null
}

// The Home dashboard's Focus panel (Decision 3, the Focus Engine) -- the
// exact shape folk.surface.focus() returns: a ranked container plus its
// server-computed `reason` string, rendered as-is, never reformatted.
export interface FocusItem {
  id: string
  tier: string
  reason: string
}

// Review queue -- mirrors web/routers/review.py's JSON shape exactly, which
// itself mirrors folk/review.py's item dicts (see that module's docstring
// for the four item types and their fields). Fields are a loose union
// across all four types rather than four separate interfaces, since the
// queue is rendered generically (grouped by `type`) the same way
// folk/cli.py's cmd_review does.
export interface ReviewBedrockPreview {
  file?: string
  section?: string
  line?: string
  diff?: string
  error?: string
}

export interface ReviewItem {
  type: 'bedrock' | 'vocab' | 'entity' | 'lint_failure'
  description: string
  counterparty?: string[]
  preview?: ReviewBedrockPreview
  // The rest of the item's fields (event_id, s, p, o, session, col, ts,
  // proposal_kind, value, slug, dup_of, errors, path, n_events, ...) vary by
  // type and are opaque to the UI -- it never inspects them, only displays
  // `description` and echoes the whole item back on accept/reject.
  [key: string]: unknown
}

export interface ReviewQueue {
  bedrock: ReviewItem[]
  vocab: ReviewItem[]
  entity: ReviewItem[]
  lint_failure: ReviewItem[]
}

export interface ReviewActionResult {
  outcome: 'accepted' | 'rejected' | 'discarded'
  diff?: string
  file?: string
}

export interface EditPreviewResult {
  diff: string
}

export interface EditCommitResult {
  committed: boolean
  reason?: string
  commit_sha?: string
  diff?: string
}

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ? String(body.detail) : `${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => null)
    throw new Error(errBody?.detail ? String(errBody.detail) : `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  collections: () => get<Collection[]>('/collections'),

  people: (collection: string, tag?: string) => {
    const params = new URLSearchParams({ collection })
    if (tag) params.set('tag', tag)
    return get<PersonSummary[]>(`/people?${params}`)
  },

  person: (slug: string, collection: string) =>
    get<PersonProfile>(`/people/${encodeURIComponent(slug)}?${new URLSearchParams({ collection })}`),

  personGraph: (slug: string, depth = 2) =>
    get<EdgeGraph>(`/graph/person/${encodeURIComponent(slug)}?depth=${depth}`),

  loci: () => get<LocusSummary[]>('/loci'),

  locus: (slug: string) => get<LocusProfile>(`/loci/${encodeURIComponent(slug)}`),

  locusGraph: (slug: string) => get<EdgeGraph>(`/graph/locus/${encodeURIComponent(slug)}`),

  locusTimeline: (slug: string) => get<LocusTimeline>(`/loci/${encodeURIComponent(slug)}/timeline`),

  agenda: (within?: number) => {
    const params = new URLSearchParams()
    if (within !== undefined) params.set('within', String(within))
    const qs = params.toString()
    return get<AgendaItem[]>(`/agenda${qs ? `?${qs}` : ''}`)
  },

  focus: (budget?: number) => {
    const params = new URLSearchParams()
    if (budget !== undefined) params.set('budget', String(budget))
    const qs = params.toString()
    return get<FocusItem[]>(`/focus${qs ? `?${qs}` : ''}`)
  },

  // Review queue (docs/design/web-ui.md Decision 2e) -- a second front-end
  // to `folk review`. reviewAction takes exactly one item per call, never a
  // list -- the containment rule (counterparty-sourced items can't be
  // batch-accepted) is enforced by this shape itself, on the server side
  // (web/routers/review.py's ReviewAction model), not just by this client
  // never offering a "select all" control.
  reviewQueue: () => get<ReviewQueue>('/review'),

  reviewAction: (item: ReviewItem, verdict: 'accept' | 'reject') =>
    post<ReviewActionResult>('/review/action', { item, verdict }),

  // Person-file write flow (Decision 1 write path #1 / Decision 2c's inline
  // edit). `section` must be one of the allowed Bedrock sections
  // (web/routers/edit.py's ALLOWED_SECTIONS) -- the server rejects anything
  // else with a 400.
  editPreview: (slug: string, collection: string, section: string, content: string) =>
    post<EditPreviewResult>(`/people/${encodeURIComponent(slug)}/edit/preview`, { collection, section, content }),

  editCommit: (slug: string, collection: string, section: string, content: string) =>
    post<EditCommitResult>(`/people/${encodeURIComponent(slug)}/edit/commit`, { collection, section, content }),
}
