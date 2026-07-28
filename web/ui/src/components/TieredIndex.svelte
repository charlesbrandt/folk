<script lang="ts">
  import type { TieredIndex } from '../lib/api'

  export let index: TieredIndex
  export let title = 'Index'

  let showSuperseded = false

  function humanize(p: string): string {
    return p.replace(/_/g, ' ')
  }
</script>

<div class="tiered-index">
  <h2>{title}</h2>
  {#if index.tiers.length === 0 && index.superseded.length === 0}
    <p class="empty">No index records yet.</p>
  {/if}

  {#each index.tiers as group (group.tier)}
    <section class="tier tier-{group.tier}">
      <h3>{group.label}</h3>
      <ul>
        {#each group.records as r}
          <li class="record">
            <span class="triple">
              <span class="subject">{r.s}</span>
              <span class="predicate">--{humanize(r.p)}--&gt;</span>
              <span class="object">{r.o}</span>
            </span>
            {#if r.staleness !== 'fresh'}
              <span class="marker marker-{r.staleness}">[{r.staleness}]</span>
            {/if}
            {#if r.note}<div class="note">{r.note}</div>{/if}
            <div class="meta">
              {#if r.src}<span>src: {r.src}</span>{/if}
              {#if r.when}<span>when: {r.when}</span>{/if}
              {#if r.last_reinforced}<span>last reinforced: {r.last_reinforced}</span>{/if}
              {#if r.reinforce_count}<span>reinforced {r.reinforce_count}×</span>{/if}
            </div>
          </li>
        {/each}
      </ul>
    </section>
  {/each}

  {#if index.superseded.length > 0}
    <section class="superseded">
      <button class="toggle" on:click={() => (showSuperseded = !showSuperseded)}>
        {showSuperseded ? '▾' : '▸'} Superseded (not current) — {index.superseded.length}
      </button>
      {#if showSuperseded}
        <ul>
          {#each index.superseded as r}
            <li class="record superseded-record">
              <span class="triple">
                <span class="subject">{r.s}</span>
                <span class="predicate">--{humanize(r.p)}--&gt;</span>
                <span class="object">{r.o}</span>
              </span>
              <span class="meta">superseded by {r.superseded_by}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
</div>

<style>
  .tiered-index {
    margin-top: 1rem;
  }
  h2 {
    font-size: 1rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 0 0 0.75rem;
  }
  .empty {
    color: #555;
    font-size: 0.85rem;
  }
  .tier {
    margin-bottom: 1rem;
    padding: 0.6rem 0.9rem;
    border-radius: 4px;
    border: 1px solid #222;
    background: #141414;
  }
  .tier h3 {
    margin: 0 0 0.5rem;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #666;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .record {
    padding: 0.35rem 0;
    border-top: 1px solid #1c1c1c;
  }
  .record:first-child {
    border-top: none;
  }
  .triple {
    font-size: 0.9rem;
  }
  .predicate {
    color: #666;
    margin: 0 0.35rem;
  }

  /* Distinct visual weight per tier, curated strongest -> interpreted
     lightest (web-ui.md Decision 2c). */
  .tier-human .subject,
  .tier-human .object {
    color: #eee;
    font-weight: 600;
  }
  .tier-observed .subject,
  .tier-observed .object {
    color: #ddd;
    font-weight: 500;
  }
  .tier-stated .subject,
  .tier-stated .object {
    color: #bbb;
    font-weight: 400;
  }
  .tier-interpreted .subject,
  .tier-interpreted .object {
    color: #999;
    font-weight: 400;
    font-style: italic;
  }
  .tier-candidate .subject,
  .tier-candidate .object {
    color: #887;
    font-style: italic;
  }

  .marker {
    margin-left: 0.5rem;
    font-size: 0.72rem;
    padding: 0.05rem 0.4rem;
    border-radius: 3px;
  }
  .marker-aging {
    color: #d9a441;
    background: #2a2210;
  }
  .marker-stale {
    color: #e06a5a;
    background: #2a1512;
  }

  .note {
    font-size: 0.8rem;
    color: #999;
    margin-top: 0.2rem;
  }
  .meta {
    font-size: 0.72rem;
    color: #555;
    display: flex;
    gap: 0.75rem;
    margin-top: 0.15rem;
  }

  .superseded {
    margin-top: 0.5rem;
  }
  .toggle {
    background: none;
    border: none;
    color: #555;
    font-size: 0.78rem;
    cursor: pointer;
    padding: 0.25rem 0;
  }
  .toggle:hover {
    color: #888;
  }
  .superseded-record {
    opacity: 0.55;
  }
  .superseded-record .subject,
  .superseded-record .object {
    text-decoration: line-through;
    color: #777;
  }
</style>
