<template>
  <div class="h-screen flex flex-col justify-center items-center">
    <div class="w-full p-10 mb-5 flex justify-center border-y-2 ">
      <div class="w-1/6 h-full"></div>
      <div class="w-4/6 h-full">
      <FormControl
        v-model="toDoValue"
        class="w-full"
        type="text"
        variant="outline"
        :placeholder="formDisplay.placeholder"
        @focus="onFocus"
        @blur="onBlur"
         @keydown.enter="console.log(toDoValue)"
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
<Sortable :data="tasks">
  <TransitionGroup
    name="task-list"
    tag="div"
    class="task-transition-group"
  >
    <div
      v-for="(task, index) in tasks"
      :key="task.id"
      class="!p-1 "
    >
      <SortableItem
        @dblclick="(e) => console.log(e.target.innerHTML)"
        :source="tasks"
        :index="index"
        class="!p-0 !m-0 w-full h-15 flex !rounded-lg border-b-2 border-white"
      >
        <ToDoContainer />
      </SortableItem>
    </div>
  </TransitionGroup>
        <div class="h-15 w-100  border-y-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
      </Sortable>
    </div>
  </div>
</template>
<script setup>
import { ListView, createListResource, FormControl } from 'frappe-ui';
import { reactive, ref, watch }  from 'vue'

import { Plus, Circle, CircleCheck, Star } from 'lucide-vue-next';
import ToDoContainer from './ToDoContainer.vue';
import { useDraggable, useDroppable } from '@vue-dnd-kit/core';
import { Sortable, SortableItem } from '../../Sortable/index';

  const tasks = ref([
    { id: 1, title: 'Complete project' },
    { id: 2, title: 'Client meeting' },
    { id: 3, title: 'Update documentation' },
    { id: 4, title: 'Fix bugs' },
  ]);




const toDoValue = ref("")
const editTodo = ref(false)

const formDisplay = reactive({
  icon: Plus,
  placeholder: "Add a ToDo"
})

function onFocus(){
  formDisplay.icon = Circle
  if (toDoValue.value === "") {
    formDisplay.placeholder = "Format ToDo under X by Y"
  }
}

function onBlur(){
  console.log("click")
    if (toDoValue.value === "") {
    formDisplay.placeholder = "Add a ToDo"  
    formDisplay.icon = Plus
  }
}





</script>
<style>
  /* TransitionGroup animations */
  .task-list-enter-active,
  .task-list-leave-active {
    transition: all 0.5s ease;
  }

  .task-list-enter-from {
    opacity: 0;
    transform: translateY(-30px);
  }

  .task-list-leave-to {
    opacity: 0;
    transform: translateY(30px);
  }

  .task-list-move {
    transition: transform 0.5s ease;
  }
</style>