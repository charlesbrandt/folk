<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type Collection, type AgendaItem, type FocusItem } from '../lib/api'

  let collections: Collection[] = []
  let loading = true
  let error = ''

  let agenda: AgendaItem[] = []
  let agendaLoading = true
  let agendaError = ''

  let focus: FocusItem[] = []
  let focusLoading = true
  let focusError = ''

  onMount(async () => {
    try {
      collections = await api.collections()
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }

    try {
      agenda = await api.agenda()
    } catch (e) {
      agendaError = String(e)
    } finally {
      agendaLoading = false
    }

    try {
      focus = await api.focus()
    } catch (e) {
      focusError = String(e)
    } finally {
      focusLoading = false
    }
  })

  // "in 5 days" per the task's example, with the two near-term cases spelled
  // out rather than "in 0 days" / "in 1 days".
  function daysUntilLabel(n: number): string {
    if (n === 0) return 'today'
    if (n === 1) return 'tomorrow'
    return `in ${n} days`
  }

  function personHref(item: AgendaItem): string | null {
    if (!item.collection) return null
    const slug = item.person_id.startsWith('person:') ? item.person_id.slice('person:'.length) : item.person_id
    return `#/people/${item.collection}/${slug}`
  }
</script>

<svelte:head><title>folk</title></svelte:head>

<div class="home">
  <section class="panel">
    <h2>Collections</h2>
    {#if loading}
      <p class="status">Loading…</p>
    {:else if error}
      <p class="error">{error}</p>
    {:else}
      <div class="collection-links">
        {#each collections as c (c.name)}
          <a class="collection-link" href="#/collections?collection={c.name}">{c.name}</a>
        {/each}
      </div>
    {/if}
    <p class="hint">
      Browse people by collection, or open <a href="#/loci">Loci</a> for Map/Timeline views.
    </p>
  </section>

  <section class="panel">
    <h2>Focus</h2>
    {#if focusLoading}
      <p class="status">Loading…</p>
    {:else if focusError}
      <p class="error">{focusError}</p>
    {:else if focus.length === 0}
      <p class="hint">Nothing ranked yet — no locus or participants in scope.</p>
    {:else}
      <ul class="focus-list">
        {#each focus as it (it.id)}
          <li>
            <span class="focus-id">{it.id}</span>
            <span class="focus-reason">{it.reason}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="panel">
    <h2>Reminders</h2>
    {#if agendaLoading}
      <p class="status">Loading…</p>
    {:else if agendaError}
      <p class="error">{agendaError}</p>
    {:else if agenda.length === 0}
      <p class="hint">No upcoming dates in the next 30 days.</p>
    {:else}
      <ul class="reminder-list">
        {#each agenda as it (it.person_id + it.date + it.label)}
          <li>
            {#if personHref(it)}
              <a class="reminder-person" href={personHref(it)}>{it.person}</a>
            {:else}
              <span class="reminder-person">{it.person}</span>
            {/if}
            <span class="reminder-label">{it.label}</span>
            <span class="reminder-days">{daysUntilLabel(it.days_until)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="panel placeholder">
    <h2>Review queue</h2>
    <p class="coming-soon">Coming in Wave 2 — a second front-end to <code>folk review</code>.</p>
  </section>
</div>

<style>
  .home {
    padding: 1.5rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1rem;
  }
  .panel {
    background: #141414;
    border: 1px solid #1c1c1c;
    border-radius: 6px;
    padding: 1rem 1.25rem;
  }
  .panel h2 {
    margin: 0 0 0.75rem;
    font-size: 0.95rem;
    color: #ccc;
  }
  .placeholder {
    opacity: 0.7;
  }
  .coming-soon {
    color: #666;
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0;
  }
  .coming-soon code {
    color: #888;
    background: #1a1a1a;
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
  }
  .collection-links {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .collection-link {
    color: #4a9eff;
    text-decoration: none;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  .collection-link:hover {
    border-color: #4a9eff;
  }
  .hint {
    color: #555;
    font-size: 0.8rem;
    margin: 0.9rem 0 0;
  }
  .hint a {
    color: #4a9eff;
  }
  .status {
    color: #555;
    font-size: 0.85rem;
  }
  .error {
    color: #f66;
    font-size: 0.85rem;
  }
  .reminder-list,
  .focus-list {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 0.85rem;
  }
  .reminder-list li,
  .focus-list li {
    padding: 0.35rem 0;
    border-bottom: 1px solid #1c1c1c;
  }
  .reminder-list li:last-child,
  .focus-list li:last-child {
    border-bottom: none;
  }
  .reminder-person {
    color: #4a9eff;
    text-decoration: none;
    font-weight: 500;
  }
  .reminder-person:hover {
    text-decoration: underline;
  }
  .reminder-label {
    color: #999;
    margin-left: 0.4rem;
  }
  .reminder-days {
    color: #666;
    margin-left: 0.4rem;
  }
  .reminder-days::before {
    content: '— ';
  }
  .focus-list li {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .focus-id {
    color: #ccc;
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .focus-reason {
    color: #777;
    font-size: 0.8rem;
  }
</style>
