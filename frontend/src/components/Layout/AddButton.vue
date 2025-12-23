<template>
    <div class="h-full flex justify-content items-center">
        <Dropdown :options="options" class="m-1">
        <Button
        class="!m-1"
        :variant="'outline'"
        theme="gray"
        size="sm"
        ><Plus :size="15"/></Button>
      </Dropdown>
    </div>
</template>
<script setup>
import 'dockview-vue/dist/styles/dockview.css'
import { Button, Dropdown } from 'frappe-ui'
import { FilePlusCorner, ChartGantt, Calendar, ListTodo, Plus } from 'lucide-vue-next'
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
