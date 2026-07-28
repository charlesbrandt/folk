<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type PersonProfile, type EdgeGraph } from '../lib/api'
  import TieredIndex from '../components/TieredIndex.svelte'
  import EgoGraph from '../components/EgoGraph.svelte'

  export let collection: string
  export let slug: string

  let person: PersonProfile | null = null
  let graph: EdgeGraph | null = null
  let loading = true
  let error = ''

  $: load(collection, slug)

  async function load(_collection: string, _slug: string) {
    loading = true
    error = ''
    person = null
    graph = null
    try {
      person = await api.person(_slug, _collection)
    } catch (e) {
      error = String(e)
      loading = false
      return
    }
    loading = false
    try {
      graph = await api.personGraph(person.slug)
    } catch (_) {
      // Association graph is a bonus panel -- a failure here (e.g. node
      // limit exceeded) shouldn't block the rest of the profile.
    }
  }

  function openNode(id: string) {
    const [kind, nodeSlug] = id.split(':', 2)
    if (kind === 'person' && person) {
      window.location.hash = `#/people/${person.collection}/${nodeSlug}`
    }
  }

  const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

  function formatMonthDay(monthDay: string): string {
    const [m, d] = monthDay.split('-').map(Number)
    return `${MONTH_NAMES[m - 1] ?? monthDay} ${d}`
  }
</script>

<svelte:head><title>{person ? `${person.name} | folk` : 'Person | folk'}</title></svelte:head>

<div class="person-page">
  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if person}
    <header>
      <h1>{person.name}</h1>
      <span class="meta">{person.collection} · {person.slug}</span>
    </header>

    {#if person.tags.length > 0}
      <div class="tags">
        {#each person.tags as t}<span class="tag">{t}</span>{/each}
      </div>
    {/if}

    {#if person.bio}
      <p class="bio">{person.bio}</p>
    {/if}

    {#if person.archetype}
      <section class="freetext">
        <h3>Archetype</h3>
        <p>{person.archetype}</p>
      </section>
    {/if}

    {#if person.voice}
      <section class="freetext">
        <h3>Voice</h3>
        <p>{person.voice}</p>
      </section>
    {/if}

    {#if person.appearance.labels.length > 0 || person.appearance.note}
      <section class="freetext">
        <h3>Appearance</h3>
        <ul class="assoc-list">
          {#each person.appearance.labels as item}
            <li><span class="assoc-type">{item.label}:</span> {item.value}</li>
          {/each}
        </ul>
        {#if person.appearance.note}
          <p>{person.appearance.note}</p>
        {/if}
        {#if Object.keys(person.appearance_checkpoints).length > 0}
          <p class="meta">Also described at: {Object.keys(person.appearance_checkpoints).join(', ')}</p>
        {/if}
      </section>
    {/if}

    {#if person.associations.length > 0}
      <section class="freetext">
        <h3>Associations</h3>
        <ul class="assoc-list">
          {#each person.associations as a}
            <li>{a.name}{#if a.type} <span class="assoc-type">({a.type})</span>{/if}</li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if person.dates.length > 0}
      <section class="freetext">
        <h3>Dates</h3>
        <ul class="dates-list">
          {#each person.dates as d}
            <li>{d.label}: {formatMonthDay(d.month_day)}{#if d.year} {d.year}{/if}</li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if graph && graph.nodes.length > 1}
      <section class="freetext">
        <h3>Map</h3>
        <EgoGraph graph={graph} onNodeClick={openNode} />
      </section>
    {/if}

    {#if person.media.length > 0}
      <section class="freetext">
        <h3>Media</h3>
        <ul class="media-list">
          {#each person.media as m}
            <li>{m.ref}{#if m.note} — {m.note}{/if}</li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if person.defining_moments.length > 0}
      <section class="freetext">
        <h3>Defining moments</h3>
        <ul>
          {#each person.defining_moments as dm}<li>{dm}</li>{/each}
        </ul>
      </section>
    {/if}

    <TieredIndex index={person.index} />
  {/if}
</div>

<style>
  .person-page {
    padding: 1.5rem;
    max-width: 780px;
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
    color: #eee;
  }
  .meta {
    color: #666;
    font-size: 0.85rem;
  }
  .tags {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.75rem;
  }
  .tag {
    font-size: 0.75rem;
    color: #999;
    background: #222;
    padding: 0.12rem 0.5rem;
    border-radius: 3px;
  }
  .bio {
    color: #ccc;
    line-height: 1.5;
    margin: 0 0 1rem;
  }
  .freetext {
    margin-bottom: 1.25rem;
  }
  .freetext h3 {
    margin: 0 0 0.4rem;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #666;
  }
  .freetext p {
    color: #bbb;
    margin: 0;
    white-space: pre-wrap;
  }
  .assoc-list,
  .media-list,
  .dates-list {
    list-style: none;
    margin: 0;
    padding: 0;
    color: #bbb;
    font-size: 0.9rem;
  }
  .assoc-list li,
  .media-list li,
  .dates-list li {
    padding: 0.2rem 0;
  }
  .assoc-type {
    color: #666;
  }
  .status {
    color: #555;
    font-size: 0.85rem;
  }
  .error {
    color: #f66;
    font-size: 0.9rem;
  }
</style>
