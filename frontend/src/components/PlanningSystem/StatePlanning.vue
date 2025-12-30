<template>
    <div class="h-[100vh]">
        <VueFlow :nodes="nodes">
          <Background/>
          <Controls />
        </VueFlow>
    </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';

//Dagre
import dagre from 'dagre';

const NODE_WIDTH = 172;
const NODE_HEIGHT = 36;

function layoutWithDagre(nodes, edges, direction = 'TB') {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction });

  const isHorizontal = direction === 'LR';

  // add nodes
  nodes.forEach((node) => {
    g.setNode(node.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    });
  });

  // add edges
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const { x, y } = g.node(node.id);

    return {
      ...node,
      position: {
        x: x - NODE_WIDTH / 2,
        y: y - NODE_HEIGHT / 2,
      },
      sourcePosition: isHorizontal ? 'right' : 'bottom',
      targetPosition: isHorizontal ? 'left' : 'top',
    };
  });

  return {
    nodes: layoutedNodes,
    edges: edges.map((e) => ({ ...e })),
  };
}
//


const nodes = ref([
  {
    id: '1',
    position: { x: 50, y: 50 },
    data: { label: 'Node 1', },
  }
]);

function addNode() {
  const id = Date.now().toString()
  
  nodes.value.push({
    id,
    position: { x: 150, y: 50 },
    data: { label: `Node ${id}`, },
  })
}


</script>
<style>
@import '@vue-flow/core/dist/style.css';

@import '@vue-flow/core/dist/theme-default.css';
</style>
