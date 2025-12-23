<template>
  <div class="flex h-screen">
    <Sidebar
      :header="header"
      :sections="sections"
    />
  </div>
</template>

<script setup>
import { Sidebar } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { FilePlusCorner, ChartGantt, Calendar, ListTodo } from 'lucide-vue-next'

const router = useRouter()


const header = {
  title: 'Kratium',
  subtitle: "Keenan's System",
    logo: '/Kratium Icon.jpg',
  menuItems: [
    {
      label: 'Toggle Theme',
      onClick() {

      },
    },
  ],
}

const sections = [
  {
    label: 'Time System',
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
    ],
  },
]
</script>