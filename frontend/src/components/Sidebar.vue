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
  title: 'My App',
  subtitle: 'John Doe',
    logo: 'https://raw.githubusercontent.com/frappe/crm/develop/.github/logo.svg',
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
        label: 'Dashboard',
        to: '/',
              onClick() {
                console.log("click")
      },
      },
      {
        label: 'Tasks',
        to: "/",                // Route (vue-router)
        onClick: () => {console.log("click")},   // Action instead of route
        // 
        onClick() {
        console.log("click")
      },
      },
    ],
  },
  {
    label: 'Views',
    collapsible: true,
    items: [
      {
        label: 'My Tasks',
        to: '/account/login',
      },
    ],
  },
]
</script>