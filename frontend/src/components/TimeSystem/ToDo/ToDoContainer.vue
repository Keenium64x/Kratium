<template>
  <div class="!p-0 !mb-2 w-full h-full !flex !rounded-lg !shadow-[0_1px_2px_rgba(0,0,0,0.2)] !bg-[#f3f3f3]">
    
    <div class="w-[5%] flex justify-start pl-4 items-center">
      <Component
        :is="isChecked"
        :fill="circleFill"
        @click="CircleClick"
        :class="circleClass"
        class="w-6 h-6 flex-shrink-0 transition-all duration-300 ease-out opacity-100 hover:opacity-80"
      />
    </div>

    <div
    class="w-full flex items-center
            pl-6 pr-6
            overflow-hidden"
    >
      <span class="whitespace-nowrap overflow-hidden text-clip">
        {{ todos }}
      </span>
    </div>

    <div class="w-[5%] flex justify-end pr-10 items-center">
      <Star
        :fill="starFill"
        @click="starClick"
        class="w-6 h-6 flex-shrink-0 transition-all duration-400 ease-out opacity-100 hover:opacity-80"
      />
    </div>

  </div>
</template>
<script setup>
import { ListView, createListResource, FormControl } from 'frappe-ui';
import { reactive, ref, watch }  from 'vue'
import { Plus, Circle, Star, CircleCheckBig, CircleCheck } from 'lucide-vue-next';
import { emitter } from '../../../event-bus';

const props = defineProps({
    todos: String,
    completed: Boolean,
    control: Object,
    id: String,
    starred: Number
})


const starFill = ref("none")
const isChecked = ref(Circle)
const circleFill = ref('none')
const circleClass = ref('')


async function starClick(){
    if (starFill.value === "none"){
        starFill.value = "black"
        await props.control.setValue.submit({
        name: props.id,
        starred: 1,
    })
        emitter.emit('todos_updated')
    }
    else{
        starFill.value = "none"
        await props.control.setValue.submit({
        name: props.id,
        starred: 0,
    })
        emitter.emit('todos_updated')        
    }
}

async function CircleClick(){
    if (isChecked.value === Circle){
        isChecked.value = CircleCheck
        circleFill.value = 'rgb(187, 247, 208)'
        circleClass.value = 'text-green-500'
        await props.control.setValue.submit({
        name: props.id,
        completed: 1,
    })
        emitter.emit('todos_updated')
    }
    else{
        isChecked.value = Circle
        circleFill.value = 'none'
        circleClass.value = ''
        await props.control.setValue.submit({
        name: props.id,
        completed: 0,
    })
        emitter.emit('todos_updated')
    }    
}

watch(
  () => props.completed,
  (val) => {
    isChecked.value = val ? CircleCheck : Circle
    circleFill.value = val ? 'rgb(187, 247, 208)' : 'none'
    circleClass.value = val ? 'text-green-500' : ''
  },
  { immediate: true }
)

watch(
  () => props.starred,
  (val) => {
    if (val === 1){
    starFill.value = "Black"
    }
  },
  { immediate: true }
)


</script>
