<script lang="ts">
  import { onMount } from 'svelte'
  import Home from './views/Home.svelte'
  import Collections from './views/Collections.svelte'
  import Person from './views/Person.svelte'
  import Loci from './views/Loci.svelte'
  import Locus from './views/Locus.svelte'
  import Review from './views/Review.svelte'
  import SiteNav from './components/SiteNav.svelte'

  type Route =
    | { view: 'home' }
    | { view: 'collections'; collection: string; tag: string }
    | { view: 'person'; collection: string; slug: string }
    | { view: 'loci' }
    | { view: 'locus'; slug: string; subview: 'map' | 'timeline' }
    | { view: 'review' }

  function parseHash(): Route {
    const raw = window.location.hash.replace(/^#\/?/, '')
    const qIdx = raw.indexOf('?')
    const pathPart = qIdx >= 0 ? raw.slice(0, qIdx) : raw
    const queryPart = qIdx >= 0 ? raw.slice(qIdx + 1) : ''
    const parts = pathPart.split('/').filter(Boolean)
    const params = new URLSearchParams(queryPart)

    if (parts[0] === 'people' && parts[1] && parts[2]) {
      return { view: 'person', collection: parts[1], slug: parts[2] }
    }
    if (parts[0] === 'loci' && parts[1]) {
      const subview = parts[2] === 'timeline' ? 'timeline' : 'map'
      return { view: 'locus', slug: parts[1], subview }
    }
    if (parts[0] === 'loci') {
      return { view: 'loci' }
    }
    if (parts[0] === 'collections') {
      return { view: 'collections', collection: params.get('collection') ?? '', tag: params.get('tag') ?? '' }
    }
    if (parts[0] === 'review') {
      return { view: 'review' }
    }
    return { view: 'home' }
  }

  let route = parseHash()

  onMount(() => {
    function onHashChange() {
      route = parseHash()
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  })

  $: navCurrent = route.view === 'person' ? 'collections' : route.view === 'locus' ? 'loci' : route.view
</script>

<div class="app">
  <header>
    <a class="brand" href="#/">folk</a>
    <SiteNav current={navCurrent} />
  </header>

  <main>
    {#if route.view === 'home'}
      <Home />
    {:else if route.view === 'collections'}
      {#key `${route.collection}:${route.tag}`}
        <Collections initialCollection={route.collection} initialTag={route.tag} />
      {/key}
    {:else if route.view === 'person'}
      <Person collection={route.collection} slug={route.slug} />
    {:else if route.view === 'loci'}
      <Loci />
    {:else if route.view === 'locus'}
      <Locus slug={route.slug} subview={route.subview} />
    {:else if route.view === 'review'}
      <Review />
    {/if}
  </main>
</div>

<style>
  :global(*, *::before, *::after) {
    box-sizing: border-box;
  }

  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, sans-serif;
    background: #111;
    color: #ddd;
  }

  :global(a) {
    color: inherit;
  }

  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  header {
    display: flex;
    align-items: center;
    gap: 2rem;
    padding: 0.75rem 1.5rem;
    background: #1a1a1a;
    border-bottom: 1px solid #333;
  }

  .brand {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: #4a9eff;
    text-decoration: none;
  }

  main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
</style>
