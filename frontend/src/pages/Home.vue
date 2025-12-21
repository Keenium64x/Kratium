<template>
  <div class="flex h-screen">
    <Sidebar />

    <div class="flex-1 flex flex-col overflow-hidden">
      <div class="border-b h-[50px] flex items-center px-4">
      </div>
      <div class="flex-1 overflow-auto">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import Sidebar from '../components/Sidebar.vue'
</script>
