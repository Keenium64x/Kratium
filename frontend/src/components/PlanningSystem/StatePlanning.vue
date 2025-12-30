<template>
    <div class="h-[100vh]">
        <VueFlow :nodes="dagreNode.nodes" :edges="dagreNode.edges" :nodes-draggable="false">
          <Background/>
        </VueFlow>
    </div>
</template>
<script setup>
import { ref, onMounted, watch, watchEffect  } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background';
import { createListResource } from 'frappe-ui'


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




const nodes = ref([]);
const edges = ref([]);

let goalNode = createListResource({
  doctype: 'Goal Node',
  fields: ['name', 'label', 'x', 'y', 'type'],
  
})
goalNode.fetch()


watch(()=>goalNode.data, (data)=>{
  data.forEach((value)=>{
    nodes.value.push({
      id: value.name,
      data: { label: value.label },
      position: { x: value.x, y: value.y}
    })
  })

  
})

let goalEdge = createListResource({
  doctype: 'Goal Edge',
  fields: ['name', 'source', 'target',],
  
})
goalEdge.fetch()

const dagreNode = ref({ nodes: [], edges: [] })

watchEffect(() => {
  if (!goalNode.data || !goalEdge.data) return

  nodes.value = goalNode.data.map(v => ({
    id: v.name,
    data: { label: v.label },
    position: { x: v.x, y: v.y },
    type: v.type
  }))

  edges.value = goalEdge.data.map(v => ({
    id: v.name,
    source: v.source,
    target: v.target,
    animated: true
  }))

  dagreNode.value = layoutWithDagre(nodes.value, edges.value)
})








</script>
<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
</style>
