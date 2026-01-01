<template>
    <div class="h-[100vh] m-2">
      <VueFlow
        :nodes="dagreNode.nodes"
        :edges="dagreNode.edges"
        :nodes-draggable="false"
        :apply-default="false"
        selection-on-drag
        multi-selection-key-code="Shift"
        @keydown.delete.prevent="deleteSelected"

      >
          <template #node-custom="nodePropsCustom">
            <CustomNode v-bind="nodePropsCustom" />
          </template>
          <template #node-cusin="nodePropsCusin">
            <CusinNode v-bind="nodePropsCusin" />
          </template>    
          <template #node-cusout="nodePropsCusout">
            <CusoutNode v-bind="nodePropsCusout" />
          </template>                   
          <Background/>
        </VueFlow>
    </div>
</template>
<script setup>
import { ref, onMounted, watch, watchEffect, onUnmounted } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background';
import { createListResource } from 'frappe-ui'
import CustomNode from './CustomNode.vue';
import CusinNode from './CusinNode.vue'
import CusoutNode from './CusoutNode.vue'
import { emitter } from '../../event-bus';


//Dagre
import dagre from 'dagre';

const NODE_WIDTH = 231;
const NODE_HEIGHT = 58;

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
const isNew = ref(false)

let goalNode = createListResource({
  doctype: 'Goal Node',
  fields: ['name', 'label', 'type', 'parent_goal_node'],
  
})
goalNode.fetch()
const dagreNode = ref({ nodes: [], edges: [] })
 
goalNode.list.promise.then(() => {
  if (isNew.value) {
    isNew.value = false
    return
  }

  goalNode.data.forEach((data) => {
    nodes.value.push({
      id: data.name,
      data: { label: data.label },
      type: data.type
    })

    if (data.parent_goal_node != null) {
      const parents = data.parent_goal_node.split(',')
      parents.forEach((value)=>{
        edges.value.push({
        id: `${value}-${data.name}`,
        source: value,
        target: data.name,
        animated: true
      })  
      })

    }
  })

  dagreNode.value = layoutWithDagre(nodes.value, edges.value)
})



//Adding action
emitter.on('goal-add-node', async (data)=>{
  function getMaxNodeIndex(goalNodeData) {
    let max = -1

    goalNodeData.forEach(node => {
      const match = node.name.match(/(\d+)$/)
      if (!match) return
      max = Math.max(max, Number(match[1]))
    })
    return max
  }

  const max = getMaxNodeIndex(goalNode.data)
  const newId = `Administrator-GN-${String(max + 1).padStart(6, '0')}`

  await goalNode.insert.submit({
    id: newId,
    label: "Add A Name...",
    parent_goal_node: data.parentId,
    type: 'custom'

  })
  
  nodes.value.push({
    id: newId,
    data: {label: "Add A Name..."},
    type: 'custom'
  })

  edges.value.push({
    id: `${data.parentId}-${newId}`,
    source: data.parentId,
    target: newId,
    animated: 'true'
  })

  dagreNode.value = layoutWithDagre(nodes.value, edges.value)    

  isNew.value = true
})



//Deleting Action
const deleteable = ref(true)


emitter.on('goal-text-edit-focus',  ()=>{
  deleteable.value = false
})

emitter.on('goal-text-edit-blur',  ()=>{
  deleteable.value = true
})

//Deleting Action
const { nodes: vfNodes, edges: vfEdges, setNodes, setEdges } = useVueFlow()

function deleteSelected() {
  if(deleteable.value){
    const selectedNodes = vfNodes.value.filter(n => n.selected)
    const selectedNodeIds = selectedNodes.map(n => n.id)

    const edgesToDelete = vfEdges.value.filter(edge =>
      selectedNodeIds.includes(edge.target) || selectedNodeIds.includes(edge.source)
    )

    const updatedNodes = vfNodes.value.filter(node => !selectedNodeIds.includes(node.id))
    const updatedEdges = vfEdges.value.filter(edge => !edgesToDelete.includes(edge))


    const nodesWithoutParents = updatedNodes.filter(node => {
      if (node.type === 'cusin') {
        return false;  // Skip input nodes
      }
    

      const hasParentEdge = updatedEdges.some(edge => edge.target === node.id)
      return !hasParentEdge
    })


    if (nodesWithoutParents.length > 0) {
      emitter.emit('toast', {
      title: "Node Deletion Error ",
      description: "Deletion would result in nodes without parent edges",
      theme: "red"
    })
      return 
    }

    selectedNodeIds.forEach((node)=>{
      goalNode.delete.submit(node)
    })    

    nodes.value = updatedNodes
    edges.value = updatedEdges

    dagreNode.value = layoutWithDagre(nodes.value , edges.value)

  }
}

const { 
  onConnect,
  onEdgeClick,
  onEdgesChange 
} = useVueFlow()

onConnect((event) => {
  const previous = goalNode.data.filter(goal => goal.name === event.target)[0].parent_goal_node

  edges.value.push({
    id: `${event.source}-${event.targe}`,
    source: event.source,
    target: event.target,
    animated: true
})  

  dagreNode.value = layoutWithDagre(nodes.value , edges.value)

  goalNode.setValue.submit({
    name: event.target,
    parent_goal_node: `${previous},${event.source}`
  })
})

onEdgeClick((event)=>{
  dagreNode.value.edges = edges.value.map(e =>
  e.id === event.edge.id
    ? { ...e, selected: true }
    : e
)


})

onEdgesChange((changes) => {
  changes.forEach(change => {
    if (change.type === 'select' && change.selected === false) {
      dagreNode.value.edges = edges.value.map(e =>
        e.id === change.id
          ? { ...e, selected: false }
          : e
      )
      
    }
  })
})

function deleteSelectedEdges(e) {
  if (e.key !== 'Delete' && e.key !== 'Backspace') return

  dagreNode.value.edges = dagreNode.value.edges.filter(
    edge => !edge.selected
  )
  console.log(dagreNode.value.edges)
}

onMounted(() => {
  window.addEventListener('keydown', deleteSelectedEdges)
})

onUnmounted(() => {
  window.removeEventListener('keydown', deleteSelectedEdges)
})


</script>
<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';

.vue-flow__edge path {
  transition: all 400ms cubic-bezier(.4,0,.2,1);
  opacity: 1;
}

.vue-flow__edge.selected path {
  opacity: 1;
  stroke-width: 3;
  filter: drop-shadow(0 0 6px rgba(0,0,0,.4));
}
</style>
