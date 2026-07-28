<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import cytoscape from 'cytoscape'
  import type { Core } from 'cytoscape'
  import type { EdgeGraph } from '../lib/api'

  export let graph: EdgeGraph
  export let onNodeClick: (id: string) => void = () => {}

  let container: HTMLDivElement
  let cy: Core | null = null

  function render() {
    if (!container) return
    if (cy) {
      cy.destroy()
      cy = null
    }
    cy = cytoscape({
      container,
      elements: [
        ...graph.nodes.map(n => ({ data: { id: n.id, label: n.label } })),
        ...graph.edges.map((e, i) => ({
          data: { id: `e${i}`, source: e.source, target: e.target, label: e.predicate.replace(/_/g, ' ') },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: any) => (String(ele.data('id')).startsWith('person:') ? '#4a9eff' : '#8a6ad8'),
            label: 'data(label)',
            color: '#ddd',
            'font-size': '11px',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 22,
            height: 22,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#3a3a3a',
            'target-arrow-color': '#3a3a3a',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '9px',
            color: '#777',
            'text-rotation': 'autorotate',
          },
        },
      ],
      layout: { name: 'cose', animate: false },
      wheelSensitivity: 0.3,
    })
    cy.on('tap', 'node', evt => {
      onNodeClick(evt.target.data('id'))
    })
  }

  onMount(render)
  onDestroy(() => cy?.destroy())

  $: if (container && graph) render()
</script>

<div class="graph-wrap" bind:this={container}></div>

<style>
  .graph-wrap {
    width: 100%;
    height: 480px;
    background: #101010;
    border: 1px solid #222;
    border-radius: 4px;
  }
</style>
