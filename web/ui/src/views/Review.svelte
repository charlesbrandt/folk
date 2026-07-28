<script lang="ts">
  import { onMount } from 'svelte'
  import { api, type ReviewQueue, type ReviewItem } from '../lib/api'

  // Mirrors folk/cli.py's REVIEW_LABELS/REVIEW_ORDER exactly (web-ui.md
  // Decision 2e / Part A step 4).
  const REVIEW_LABELS: Record<string, string> = {
    vocab: 'Vocab proposals',
    entity: 'Entity-resolution proposals',
    bedrock: 'Bedrock suggestions',
    lint_failure: 'Lint failures',
  }
  const REVIEW_ORDER = ['vocab', 'entity', 'bedrock', 'lint_failure'] as const

  let queue: ReviewQueue | null = null
  let loading = true
  let error = ''
  // event_id (or session, for lint_failure items, which have none) of an
  // item currently mid-request -- disables its own buttons only, never a
  // global "select all"/batch control. There is intentionally no such
  // control anywhere in this view: the API only ever takes one item per
  // call (web/routers/review.py's ReviewAction.item is a single object, not
  // a list), so a batch action has nothing to call even if a button existed.
  let pending: Set<string> = new Set()
  let actionError = ''

  onMount(load)

  async function load() {
    loading = true
    error = ''
    try {
      queue = await api.reviewQueue()
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }
  }

  function itemKey(item: ReviewItem): string {
    return String(item.event_id ?? item.session ?? item.slug ?? JSON.stringify(item))
  }

  async function act(item: ReviewItem, verdict: 'accept' | 'reject') {
    const key = itemKey(item)
    pending = new Set(pending).add(key)
    actionError = ''
    try {
      await api.reviewAction(item, verdict)
      // Re-fetch rather than locally patch the list -- the queue is derived
      // fresh from the journal every time (folk review's own design), and
      // this keeps the UI's view of "what's pending" always exactly what
      // the next `folk review` run would also see.
      await load()
    } catch (e) {
      actionError = String(e)
      pending = new Set(pending)
      pending.delete(key)
    }
  }

  $: total = queue ? REVIEW_ORDER.reduce((n, k) => n + queue![k].length, 0) : 0
</script>

<svelte:head><title>Review queue | folk</title></svelte:head>

<div class="review-page">
  <header>
    <h1>Review queue</h1>
    <p class="hint">
      A second front-end to <code>folk review</code> -- every accept/reject here does exactly what the
      same action would do at the terminal: a journal <code>review</code> event, or a person-file edit
      shown as a diff first. Items from a session with an external counterparty are always reviewed
      one at a time -- there is no "select all" here, for any item type.
    </p>
  </header>

  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if queue}
    {#if actionError}
      <p class="error">{actionError}</p>
    {/if}

    {#if total === 0}
      <p class="empty">(review queue is empty)</p>
    {/if}

    {#each REVIEW_ORDER as kind}
      {#if queue[kind].length > 0}
        <section class="group">
          <h2>{REVIEW_LABELS[kind]} ({queue[kind].length})</h2>
          <ul>
            {#each queue[kind] as item (itemKey(item))}
              <li class="item" class:counterparty={!!item.counterparty}>
                {#if item.counterparty}
                  <div class="warning">
                    ⚠ external counterparty: {item.counterparty.join(', ')} -- review individually
                  </div>
                {/if}
                <pre class="description">{item.description}</pre>

                {#if item.type === 'bedrock' && item.preview}
                  {#if item.preview.error}
                    <p class="preview-error">preview error: {item.preview.error}</p>
                  {:else if item.preview.diff}
                    <pre class="diff">{item.preview.diff}</pre>
                  {:else}
                    <p class="no-op">(already present in {item.preview.file} -- accepting just records the decision)</p>
                  {/if}
                {/if}

                <div class="actions">
                  {#if kind !== 'lint_failure'}
                    <button
                      class="accept"
                      disabled={pending.has(itemKey(item))}
                      on:click={() => act(item, 'accept')}
                    >
                      Accept
                    </button>
                  {/if}
                  <button
                    class="reject"
                    disabled={pending.has(itemKey(item))}
                    on:click={() => act(item, 'reject')}
                  >
                    {kind === 'lint_failure' ? 'Discard' : 'Reject'}
                  </button>
                </div>
              </li>
            {/each}
          </ul>
        </section>
      {/if}
    {/each}
  {/if}
</div>

<style>
  .review-page {
    padding: 1.5rem;
    max-width: 780px;
  }
  header {
    margin-bottom: 1.25rem;
  }
  h1 {
    margin: 0 0 0.5rem;
    font-size: 1.5rem;
    color: #eee;
  }
  .hint {
    color: #888;
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0;
  }
  .hint code {
    color: #aaa;
    background: #1a1a1a;
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
  }
  .group {
    margin-bottom: 1.5rem;
  }
  .group h2 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #666;
    margin: 0 0 0.6rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .item {
    background: #141414;
    border: 1px solid #1c1c1c;
    border-radius: 6px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.75rem;
  }
  .item.counterparty {
    border-color: #6a3a1a;
  }
  .warning {
    color: #d9a441;
    font-size: 0.78rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .description {
    color: #ccc;
    font-size: 0.85rem;
    font-family: inherit;
    white-space: pre-wrap;
    margin: 0 0 0.5rem;
  }
  .diff {
    background: #0d0d0d;
    border: 1px solid #222;
    border-radius: 4px;
    padding: 0.6rem 0.75rem;
    font-size: 0.78rem;
    color: #bbb;
    overflow-x: auto;
    margin: 0 0 0.6rem;
  }
  .preview-error {
    color: #e06a5a;
    font-size: 0.8rem;
    margin: 0 0 0.6rem;
  }
  .no-op {
    color: #666;
    font-size: 0.8rem;
    margin: 0 0 0.6rem;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
  }
  button {
    border-radius: 4px;
    padding: 0.35rem 0.9rem;
    font-size: 0.82rem;
    cursor: pointer;
    border: 1px solid #2a2a2a;
    background: #1a1a1a;
    color: #ccc;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button.accept {
    color: #6fbf73;
    border-color: #2a4a2a;
  }
  button.accept:hover:not(:disabled) {
    border-color: #6fbf73;
  }
  button.reject {
    color: #e06a5a;
    border-color: #4a2a2a;
  }
  button.reject:hover:not(:disabled) {
    border-color: #e06a5a;
  }
  .status,
  .empty {
    color: #555;
    font-size: 0.85rem;
  }
  .error {
    color: #f66;
    font-size: 0.9rem;
  }
</style>
