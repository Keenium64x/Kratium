<template>
  <div class="flex h-screen">
    <Sidebar />

    <div class="flex-1 flex flex-col overflow-hidden">
      <div class="border-b h-[50px] flex items-center px-4">
        <button @click="close">reset</button>

      </div>
      <div class="flex-1 overflow-auto">
            <dockview-vue
            style="width:100%;height:100%"
            :theme="themeLightSpaced"
            watermark-component="watermarkComponent"
            @ready="onReady"
          />
          
      </div>
    </div>
  </div>
</template>

<script setup>
import { Plus } from 'lucide-vue-next';
import Sidebar from '../components/Sidebar.vue'
import { DockviewVue } from 'dockview-vue'
import 'dockview-vue/dist/styles/dockview.css'
import { themeLightSpaced } from 'dockview-vue'

import { setDockviewApi, getDockviewApi } from './dockviewApi'

import WatermarkPanel from './WatermarkPanel.vue'
import Gantt from '../components/Gantt.vue'
import Calendar from '../components/Calendar.vue'

import { useRoute, useRouter } from 'vue-router'
import { watch, ref } from 'vue';



//Docking
defineOptions({
  components: {
    'dockview-vue': DockviewVue,
    watermarkComponent: WatermarkPanel,
    Gantt: Gantt,
    Calendar: Calendar
  },
})

const components = []

const panels = ref([])

const route = useRoute()

function onReady(event) {
  const eventApi = event.api
  setDockviewApi(eventApi)
  
  const savedLayout = localStorage.getItem('my_layout')
  let restored = false

  if (savedLayout) {
    try {
      eventApi.fromJSON(JSON.parse(savedLayout))
      restored = true
    } catch (e) {
      console.warn('Failed to restore layout:', e)
    }
  }

  panels.value = Object.values(eventApi.panels).map(p => p.id)
      if (!panels.value.includes(route.name)){
        eventApi.addPanel({id: route.name, component: route.name})
      }


  eventApi.onDidLayoutChange(() => {
    const layout = eventApi.toJSON()
    localStorage.setItem('my_layout', JSON.stringify(layout))
  })
}



watch(
  () => route.name,
  (name) => {
    const api = getDockviewApi()
    panels.value = Object.values(api.panels).map(p => p.id)

    if (!panels.value.includes(name)){
      api.addPanel({id: name, component: name})
    }
  
  },

)
function close() {
  localStorage.clear()
}

</script>
