<script lang="ts">
  import { api, type LocusProfile, type EdgeGraph, type LocusTimeline } from '../lib/api'
  import TieredIndex from '../components/TieredIndex.svelte'
  import EgoGraph from '../components/EgoGraph.svelte'

  export let slug: string
  export let subview: 'map' | 'timeline' = 'map'

  let locusData: LocusProfile | null = null
  let graph: EdgeGraph | null = null
  let timeline: LocusTimeline | null = null
  let loading = true
  let error = ''

  $: load(slug)
  $: if (locusData) loadSubview(subview)

  async function load(_slug: string) {
    loading = true
    error = ''
    locusData = null
    graph = null
    timeline = null
    try {
      locusData = await api.locus(_slug)
    } catch (e) {
      error = String(e)
      loading = false
      return
    }
    loading = false
    await loadSubview(subview)
  }

  async function loadSubview(view: 'map' | 'timeline') {
    if (!locusData) return
    if (view === 'map' && !graph) {
      try {
        graph = await api.locusGraph(locusData.slug)
      } catch (e) {
        error = String(e)
      }
    } else if (view === 'timeline' && !timeline) {
      try {
        timeline = await api.locusTimeline(locusData.slug)
      } catch (e) {
        error = String(e)
      }
    }
  }

  function switchView(view: 'map' | 'timeline') {
    window.location.hash = `#/loci/${slug}/${view}`
  }

  function openNode(id: string) {
    const [kind, nodeSlug] = id.split(':', 2)
    if (kind === 'person') {
      // A cast member's home collection isn't carried on the graph node --
      // route through the person's own default collection lookup isn't
      // available here, so send them to the collections browser filtered
      // to nothing and let the person page's own collection resolution
      // (from the Locus's cast association, which does carry a ref) apply.
      // Simplest correct behavior for v1: try the Locus's own collection.
      window.location.hash = `#/people/${locusData?.collection ?? ''}/${nodeSlug}`
    }
  }
</script>

<svelte:head><title>{locusData ? `${locusData.name} | folk` : 'Locus | folk'}</title></svelte:head>

<div class="locus-page">
  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if locusData}
    <header>
      <h1>{locusData.name}</h1>
      <span class="meta">locus:{locusData.slug}{locusData.collection ? ` · ${locusData.collection}` : ''}</span>
    </header>

    {#if locusData.tags.length > 0}
      <div class="tags">
        {#each locusData.tags as t}<span class="tag">{t}</span>{/each}
      </div>
    {/if}

    {#if locusData.genius_loci}
      <section class="freetext">
        <h3>Genius Loci</h3>
        <p>{locusData.genius_loci}</p>
      </section>
    {/if}

    {#if locusData.associations.length > 0}
      <section class="freetext">
        <h3>Cast</h3>
        <ul class="assoc-list">
          {#each locusData.associations as a}
            <li>{a.name}{#if a.type} <span class="assoc-type">({a.type})</span>{/if}</li>
          {/each}
        </ul>
      </section>
    {/if}

    <div class="subview-tabs">
      <button class:active={subview === 'map'} on:click={() => switchView('map')}>Map</button>
      <button class:active={subview === 'timeline'} on:click={() => switchView('timeline')}>Timeline</button>
    </div>

    {#if subview === 'map'}
      {#if graph}
        {#if graph.nodes.length === 0}
          <p class="empty">No cast associations curated for this Locus yet.</p>
        {:else}
          <EgoGraph graph={graph} onNodeClick={openNode} />
        {/if}
      {:else}
        <p class="status">Loading map…</p>
      {/if}
    {:else if subview === 'timeline'}
      {#if timeline}
        {#if timeline.events.length === 0}
          <p class="empty">
            No locus-tagged journal events yet — a source adapter needs to declare
            <code>locus: {locusData.slug}</code> on the events it writes (loci.md Decision 2) before
            anything shows up here.
          </p>
        {:else}
          <ul class="timeline">
            {#each timeline.events as e}
              <li>
                <span class="when">{e.when ?? e.last_reinforced ?? ''}</span>
                <span class="triple">{e.s} --{e.p.replace(/_/g, ' ')}--&gt; {e.o}</span>
                {#if e.note}<div class="note">{e.note}</div>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      {:else}
        <p class="status">Loading timeline…</p>
      {/if}
    {/if}

    <TieredIndex index={locusData.index} title="Full index" />
  {/if}
</div>

<style>
  .locus-page {
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
  .freetext {
    margin-bottom: 1rem;
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
  .assoc-list {
    list-style: none;
    margin: 0;
    padding: 0;
    color: #bbb;
    font-size: 0.9rem;
  }
  .assoc-list li {
    padding: 0.2rem 0;
  }
  .assoc-type {
    color: #666;
  }
  .subview-tabs {
    display: flex;
    gap: 0.4rem;
    margin: 1rem 0 0.75rem;
  }
  .subview-tabs button {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #999;
    border-radius: 4px;
    padding: 0.35rem 0.8rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .subview-tabs button.active {
    color: #4a9eff;
    border-color: #4a9eff;
  }
  .timeline {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .timeline li {
    padding: 0.5rem 0;
    border-top: 1px solid #1c1c1c;
  }
  .timeline li:first-child {
    border-top: none;
  }
  .when {
    color: #4a9eff;
    font-size: 0.78rem;
    margin-right: 0.6rem;
  }
  .triple {
    color: #ccc;
    font-size: 0.88rem;
  }
  .note {
    color: #999;
    font-size: 0.82rem;
    margin-top: 0.2rem;
  }
  .status,
  .empty {
    color: #555;
    font-size: 0.85rem;
    max-width: 560px;
    line-height: 1.5;
  }
  .empty code {
    color: #888;
    background: #1a1a1a;
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
  }
  .error {
    color: #f66;
    font-size: 0.9rem;
  }
</style>
