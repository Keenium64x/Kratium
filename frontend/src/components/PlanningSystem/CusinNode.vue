<template>
  <div
    tabindex="0"
    @dblclick="onDbclick"
    :class="[
      'relative border bg-white rounded-md px-6 py-4 min-w-[231px] min-h-[58px] text-[15px] text-sm transition outline-none flex items-center justify-center outline-none',
      'shadow-[0_6px_16px_rgba(0,0,0,0.12),inset_0_0_0_1px_rgba(0,0,0,0.12)] hover:shadow-[0_8px_20px_rgba(0,0,0,0.16),inset_0_0_0_1px_rgba(0,0,0,0.14)]',
      selected 
        ? 'border-black shadow-[0_10px_24px_rgba(0,0,0,0.22),inset_0_0_0_1px_rgba(0,0,0,0.25)]'
        : selected
          ? 'border-black ring-2 ring-black/30 shadow-[0_8px_20px_rgba(0,0,0,0.18),inset_0_0_0_1px_rgba(0,0,0,0.18)]'
          : 'border-gray-300'
    ]"      
  >

    <div class="text-center text-gray-800 select-none leading-snug">
      {{ data.label }}
    </div>

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


function onDbclick(event) {
const el = event.target.closest('[data-id]')
const id = el?.dataset.id

  emitter.emit('goal-open-node', { id: id })
}

</script>