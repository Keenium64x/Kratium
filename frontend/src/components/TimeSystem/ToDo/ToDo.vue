<template>
  <div class="h-screen flex flex-col justify-center items-center">
    <div class="w-full p-10 mb-5 flex justify-center border-y-2 ">
      <div class="w-1/6 h-full"></div>
      <div class="w-4/6 h-full">
      <FormControl
        class="w-full"
        type="text"
        variant="outline"
        :placeholder="formDisplay.placeholder"
        @focus="onFocus"
        @blur="onBlur"
        @keydown.enter="console.log('ToDo')"
        size="xl"
      >
        <template #prefix>
          <Component :is="formDisplay.icon" :size="20" />
        </template>
      </FormControl>
      </div>
      <div class="w-1/6"></div>
    </div>
    
    <div class="w-full h-full">
      <ToDoContainer :pop="true"/>
      <ToDoContainer :pop="true"/>
      <ToDoContainer />
      <ToDoContainer />
    </div>
  </div>
</template>
<script setup>
import { ListView, createListResource, FormControl } from 'frappe-ui';
import { reactive, ref, watch }  from 'vue'
import CreateToDoForm from './CreateToDoForm.vue';
import { Plus, Circle, Star } from 'lucide-vue-next';
import ToDoContainer from './ToDoContainer.vue';
import { useDraggable, useDroppable } from '@vue-dnd-kit/core';

const ToDo = ref(false)
const borderCon = ref("")

const formDisplay = reactive({
  icon: Plus,
  placeholder: "Add a ToDo"
})

function onFocus(){
  formDisplay.icon = Circle
  formDisplay.placeholder = "Format ToDo under X by Y"
}

function onBlur(){
  formDisplay.icon = Plus
  formDisplay.placeholder = "Add a ToDo"  
}


</script>
