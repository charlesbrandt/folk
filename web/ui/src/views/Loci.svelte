<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type LocusSummary } from '../lib/api'

  let loci: LocusSummary[] = []
  let loading = true
  let error = ''

  onMount(async () => {
    try {
      loci = await api.loci()
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }
  })
</script>

<svelte:head><title>Loci | folk</title></svelte:head>

<div class="loci">
  <h1>Loci</h1>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="status">Loading…</p>
  {:else if loci.length === 0}
    <p class="empty">
      No Locus files registered yet — see <code>docs/design/loci.md</code> Decision 4 for how a
      collection's <code>loci/</code> subdirectory (or an explicit <code>~/.config/folk/loci-roots</code>
      entry) registers one.
    </p>
  {:else}
    <div class="grid">
      {#each loci as l (l.slug)}
        <a class="card" href="#/loci/{l.slug}">
          <span class="name">{l.name}</span>
          <span class="slug">locus:{l.slug}{l.collection ? ` · ${l.collection}` : ''}</span>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  .loci {
    padding: 1.5rem;
  }
  h1 {
    margin: 0 0 1rem;
    font-size: 1.3rem;
    color: #eee;
  }
  .status,
  .empty {
    color: #555;
    font-size: 0.85rem;
    max-width: 520px;
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
</style>
