<template>
<div class="flex-1 overflow-auto w-full ">
    <div class="h-15 mx-15" :class="borderClass">
    <div v-if="borderCon" class="w-full h-[97%] flex rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.2)] bg-[#f3f3f3]">
        <div class="w-1/6 flex justify-start pl-10 items-center">
        <Component :is="isChecked" :fill="circleFill" @click="CircleClick" :class="circleClass" class="transition-all duration-300 ease-out opacity-100 scale-200 hover:opacity-80 hover:scale-110"/>
        </div>
        <div class="w-5/6 flex justify-start items-center">
        ToDo
        </div>
        <div class="w-2/6 flex justify-end pr-10 items-center">
        <Star :fill="starFill" @click="starClick" class="transition-all duration-400 ease-out opacity-100 scale-200 hover:opacity-80 hover:scale-90"/>
        </div>
    </div>
    </div>
</div>
</template>
<script setup>
import { ListView, createListResource, FormControl } from 'frappe-ui';
import { reactive, ref, watch }  from 'vue'
import CreateToDoForm from './CreateToDoForm.vue';
import { Plus, Circle, Star, CircleCheckBig, CircleCheck } from 'lucide-vue-next';


const props = defineProps({
  pop: Boolean,
})

const borderClass = ref('border-t-2')
const borderCon = ref(false)
const starFill = ref("none")
const isChecked = ref(Circle)
const circleFill = ref('none')
const circleClass = ref('')

if (!props.pop) {
  borderClass.value = 'border-t-2 border-white'
  borderCon.value = true
}

function starClick(){
    if (starFill.value === "none"){
        starFill.value = "black"
    }
    else{
        starFill.value = "none"
    }
}

function CircleClick(){
    if (isChecked.value === Circle){
        isChecked.value = CircleCheck
        circleFill.value = 'rgb(187, 247, 208)'
        circleClass.value = 'text-green-500'
    }
    else{
        isChecked.value = Circle
        circleFill.value = 'none'
        circleClass.value = ''
    }    
}

</script>
