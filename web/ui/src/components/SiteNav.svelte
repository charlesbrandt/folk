<script lang="ts">
  export let current: string | null
</script>

<nav>
  <a href="#/" class:active={current === 'home'}>Home</a>
  <a href="#/collections" class:active={current === 'collections'}>People</a>
  <a href="#/loci" class:active={current === 'loci'}>Loci</a>
  <a href="#/review" class:active={current === 'review'}>Review</a>
</nav>

<style>
  nav {
    display: flex;
    gap: 1.25rem;
  }
  a {
    color: #888;
    text-decoration: none;
    font-size: 0.9rem;
  }
  a:hover {
    color: #eee;
  }
  a.active {
    color: #4a9eff;
  }
</style>
