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

const header = {
  title: 'Kratium',
  subtitle: 'Keenan System',
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
    items: [
      {
        label: "Gantt",
        to: "/gantt"
      },
      {
        label: "Calendar",
        to: "/calendar"
      }      
    ],
  },
]
</script>