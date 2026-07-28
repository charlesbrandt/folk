<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type Collection, type PersonSummary } from '../lib/api'

  export let initialCollection = ''
  export let initialTag = ''

  let collections: Collection[] = []
  let selected = initialCollection
  let tag = initialTag

  let people: PersonSummary[] = []
  let loading = true
  let error = ''

  onMount(async () => {
    try {
      collections = await api.collections()
      if (!selected && collections.length > 0) selected = collections[0].name
    } catch (e) {
      error = String(e)
      loading = false
      return
    }
    await load()
  })

  async function load() {
    if (!selected) return
    loading = true
    error = ''
    try {
      people = await api.people(selected, tag || undefined)
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }
    syncHash()
  }

  function syncHash() {
    const params = new URLSearchParams({ collection: selected })
    if (tag) params.set('tag', tag)
    window.location.hash = `#/collections?${params}`
  }

  function selectCollection(name: string) {
    selected = name
    tag = ''
    load()
  }

  let tagInput = tag
  function applyTag() {
    tag = tagInput.trim()
    load()
  }
</script>

<svelte:head><title>People | folk</title></svelte:head>

<div class="collections">
  <div class="collection-tabs">
    {#each collections as c (c.name)}
      <button class:active={c.name === selected} on:click={() => selectCollection(c.name)}>{c.name}</button>
    {/each}
  </div>

  <div class="filter-bar">
    <input
      type="text"
      placeholder="Filter by tag…"
      bind:value={tagInput}
      on:keydown={(e) => e.key === 'Enter' && applyTag()}
    />
    <button on:click={applyTag}>Apply</button>
    {#if tag}
      <button class="clear" on:click={() => { tagInput = ''; applyTag() }}>Clear ({tag})</button>
    {/if}
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="status">Loading…</p>
  {:else}
    <p class="status">{people.length} {people.length === 1 ? 'person' : 'people'} in {selected}{tag ? ` tagged '${tag}'` : ''}</p>
    <div class="grid">
      {#each people as p (p.slug)}
        <a class="card" href="#/people/{p.collection}/{p.slug}">
          <span class="name">{p.name}</span>
          <span class="slug">{p.slug}</span>
        </a>
      {/each}
      {#if people.length === 0}
        <p class="empty">No people found.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .collections {
    padding: 1.5rem;
  }
  .collection-tabs {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }
  .collection-tabs button {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #999;
    border-radius: 4px;
    padding: 0.35rem 0.8rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .collection-tabs button.active {
    color: #4a9eff;
    border-color: #4a9eff;
  }
  .filter-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    align-items: center;
  }
  .filter-bar input {
    padding: 0.4rem 0.7rem;
    font-size: 0.9rem;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    background: #1a1a1a;
    color: #eee;
    max-width: 260px;
  }
  .filter-bar button {
    background: none;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    color: #999;
    padding: 0.35rem 0.7rem;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .filter-bar button:hover {
    color: #4a9eff;
    border-color: #4a9eff;
  }
  .filter-bar .clear {
    color: #f66;
  }
  .status {
    color: #555;
    font-size: 0.85rem;
    margin-bottom: 1rem;
  }
  .error {
    color: #f66;
    font-size: 0.9rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    background: #141414;
    border: 1px solid #1c1c1c;
    border-radius: 6px;
    padding: 0.75rem 0.9rem;
    text-decoration: none;
  }
  .card:hover {
    border-color: #4a9eff;
  }
  .name {
    color: #eee;
    font-size: 0.95rem;
  }
  .slug {
    color: #555;
    font-size: 0.75rem;
  }
  .empty {
    color: #555;
    font-size: 0.85rem;
  }
</style>
