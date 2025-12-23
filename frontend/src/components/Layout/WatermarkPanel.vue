<template>
  <div class="flex justify-center items-center h-full bg-[#f6f5fa]">
    <div class="border h-1/4 w-1/3 bg-white flex justify-center items-center rounded-2xl">
      <Dropdown :options="options" class="m-2">
        <Button
        class="!m-3"
        :variant="'outline'"
        theme="gray"
        size="lg"
        ><FilePlusCorner /></Button>
        Add Component!
      </Dropdown>
    </div>
  </div>
</template>
<script setup>
import 'dockview-vue/dist/styles/dockview.css'
import { Button, Dropdown } from 'frappe-ui'
import { FilePlusCorner, ChartGantt, Calendar, ListTodo } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const router = useRouter()

const options = [{
    group: 'Time System',
    items: [
      {
        label: 'Gantt',
        icon: ChartGantt, 
        onClick: () => {
          router.push('/').then(()=>{
            router.push('/gantt').then(() => {
              router.push('/')
            })
          })
          }
      },
      {
        label: 'Calendar',
        icon: Calendar, 
        onClick: () => {
          router.push('/').then(()=>{
            router.push('/calendar').then(() => {
              router.push('/')
            })
          })
          }
      },
      {
        label: 'ToDo',
        icon: ListTodo, 
        onClick: () => {
          router.push('/').then(()=>{
            router.push('/todo').then(() => {
              router.push('/')
            })
          })
          }
      },
        ]     
    } 
]


</script>
