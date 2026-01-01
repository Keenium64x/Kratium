<template>
  <div
    tabindex="0"
    @keydown.delete.prevent="onDelete"
    :class="[
      'relative bg-white border rounded-md px-7 py-5 min-w-[231px] min-h-[58px] text-[15px] transition outline-none flex items-center justify-center',
      selected
        ? 'border-black shadow-lg ring-2 ring-black/30'
        : 'border-gray-300'
    ]"
  >
    <!-- Label display -->
    <div class="text-center text-gray-800 select-none leading-snug">
      {{ data.label }}
    </div>

    <!-- Invisible but selectable bottom handle -->
    <Handle
      type="source"
      position="bottom"
      class="!bg-gray-500 !z-20 opacity-0 pointer-events-auto"
    />

    <!-- Add button -->
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
import { Handle } from '@vue-flow/core'
import { Plus } from 'lucide-vue-next'
import { emitter } from '../../event-bus'

const props = defineProps({
  id: String,
  data: Object,
  selected: Boolean
})

function onAdd() {
  emitter.emit('goal-add-node', {
    parentId: props.id
  })
}

function onDelete() {
  emitter.emit('goal-delete-node', {
    parentId: props.id
  })
}
</script>