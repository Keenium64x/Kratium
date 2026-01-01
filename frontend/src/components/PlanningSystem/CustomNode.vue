<template>
  <div
    tabindex="0"
    @keydown.delete.self.prevent="onDelete"
    @keydown.backspace.self.prevent="onDelete"
    :class="[
      'relative bg-white border rounded-md px-6 py-4 min-w-[172px] text-sm transition outline-none',
      selected && isEditing
        ? 'border-black'
        : selected
          ? 'border-black shadow-lg ring-2 ring-black/30'
          : 'border-gray-300'
    ]"
  >
    <Handle
      type="target"
      position="top"
      class="!bg-gray-500"
    />

    <input
      v-model="nodeLabel"
      :placeholder="data.label"
      class="w-full text-center p-0 bg-transparent border-0 outline-none ring-0
             focus:outline-none focus:ring-0 focus:border-0
             appearance-none 
             placeholder-gray-400 text-gray-800"
      @focus="onFocus"
      @blur="onBlur"
      @keydown.enter.prevent="onEnter"
      @keydown.delete.stop
      @keydown.backspace.stop
    />

    <Handle
      type="source"
      position="bottom"
      class="!bg-gray-500 !z-20 opacity-0 pointer-events-auto"
    />

    <div
      class="absolute left-1/2 translate-x-[-50%] bottom-[-14px]
             w-7 h-7 rounded-full bg-white border border-gray-300
             flex items-center justify-center pointer-events-none"
    >
      <button
        class="pointer-events-auto w-full h-full flex items-center justify-center"
        @click.stop="onAdd"
      >
        <Plus class="w-4 h-4 text-gray-600" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Handle } from '@vue-flow/core'
import { Plus } from 'lucide-vue-next'
import { emitter } from '../../event-bus'
import { createDocumentResource, Button } from 'frappe-ui'

const props = defineProps({
  id: String,
  data: Object,
  selected: Boolean
})

const nodeLabel = ref(props.data.label)

let goalNode = createDocumentResource({
  doctype: 'Goal Node',
  name: props.id,
})

function onEnter() {
  goalNode.setValue.submit({
    name: props.id,
    label: nodeLabel.value
  })
}

const isEditing = ref(false)
const labelref= ref(nodeLabel.value)

function onFocus() {
  isEditing.value = true
  emitter.emit('goal-text-edit-focus')
}

function onBlur() {
  isEditing.value = false
  if (nodeLabel.value != labelref.value){
    goalNode.setValue.submit({
    name: props.id,
    label: nodeLabel.value
  })  
  }
  emitter.emit('goal-text-edit-blur')
}

function onAdd() {
  emitter.emit('goal-add-node', { parentId: props.id })
}

function onDelete() {
  emitter.emit('goal-delete-node', { parentId: props.id })
}
</script>