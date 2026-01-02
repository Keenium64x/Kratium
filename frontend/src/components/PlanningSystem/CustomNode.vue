<template>
  <div
    tabindex="0"
    @keydown.delete.self.prevent="onDelete"
    @keydown.backspace.self.prevent="onDelete"
    @dblclick="onDbclick"
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
      :label="id"
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
      <Popover>
        <template #target="{ togglePopover }">
          <button
              class="pointer-events-auto w-full h-full flex items-center justify-center"
              @click.stop="togglePopover"
            >
              <Plus class="w-4 h-4 text-gray-600" />
            </button>
        </template>    
        <template #body-main>
          <div >
            <div v-if="!enterNameCon" class="flex flex-col space-y-2 p-2 text-ink-gray-9">
              <Button
              :variant="'outline'"
              size="lg"
              @click.stop="enterName('custom')"
              >
              ▲ State Goal
              </Button>
              <Button
              :variant="'outline'"
              size="lg"
              @click.stop="enterName('cusout')"
              >
              ■  Base Goal
              </Button>    
            </div>  
            <div v-if="enterNameCon" class="p-4">
                <FormControl
                  :type="'text'"
                  size="lg"
                  variant="subtle"
                  placeholder="Finish Studies"
                  label="Enter Name"
                  v-model="NameInput"
                  @keydown.enter.prevent="onAdd()"
                />
            </div>      
          </div>
        </template>  
      </Popover>  
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Handle } from '@vue-flow/core'
import { Plus } from 'lucide-vue-next'
import { emitter } from '../../event-bus'
import { createDocumentResource, Button, Popover, FormControl } from 'frappe-ui'

const popover = ref(true)
const enterNameCon = ref(false)
const type = ref('custom')
const NameInput = ref('')

function enterName(nodeType){
  enterNameCon.value = true
  type.value = nodeType
}

function onAdd() {
  emitter.emit('goal-add-node', { parentId: props.id, type: type.value, name: NameInput.value })
  enterNameCon.value = false
}

const props = defineProps({
  id: String,
  data: Object,
  selected: Boolean
})

watch(
  () => props.selected,
  (isSelected) => {
    if (isSelected && !isEditing.value) {
      emitter.emit('goal-node-selected', { id: props.id })
    }
  }
)



const nodeLabel = ref(props.data.label)

let goalNode = createDocumentResource({
  doctype: 'Action',
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

function onDelete() {
  emitter.emit('goal-delete-node', { parentId: props.id })
}

function onDbclick(event) {
  const el = event.target instanceof HTMLInputElement
    ? event.target
    : event.currentTarget.querySelector('input')

  const label = el?.getAttribute('label')
  emitter.emit('goal-open-node', { id: label })
}



</script>