<template>
  <div
    tabindex="0"
    @keydown.delete.prevent="onDelete"
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
      v-model="localLabel"
      :placeholder="data.label"
      class="w-full text-center p-0 bg-transparent border-0 outline-none ring-0
             focus:outline-none focus:ring-0 focus:border-0
             appearance-none 
             placeholder-gray-400 text-gray-800"
      @focus="onFocus"
      @blur="onBlur"
      @keydown.enter.prevent="onEnter"
    />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Handle } from '@vue-flow/core'
import { emitter } from '../../event-bus'

const props = defineProps({
  id: String,
  data: Object,
  selected: Boolean
})

const localLabel = ref(props.data.label)

watch(localLabel, (v) => {
  props.data.label = v
})

function onEnter() {}

const isEditing = ref(false)

function onFocus() {
  isEditing.value = true
  emitter.emit('goal-text-edit-focus')
}

function onBlur() {
  isEditing.value = false
  emitter.emit('goal-text-edit-blur')
}

function onDelete() {
  emitter.emit('goal-delete-node', {
    parentId: props.id
  })
}
</script>