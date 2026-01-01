<template>
    <div class="flex h-screen" >
    <Sidebar />
    <div class="flex-1 flex flex-col overflow-hidden">
      <div class="border-b h-[50px] flex items-center px-4">
        <Breadcrumbs 
          :items="breadcrumbItems"
        >
        <template #prefix="{ item }">
          <component
            :is="item.icon"
            :size="15"
            class="mr-1"
          />
        </template>    
      </Breadcrumbs>
  

      </div>
      <div class="flex-1 overflow-auto">
            <router-view v-if="!isInComponents"/>
            <dockview-vue v-if="isInComponents"
            style="width:100%;height:100%"
            :theme="themeLightSpaced"
            watermark-component="watermarkComponent"
            leftHeaderActionsComponent="AddButton"
            @ready="onReady"
          />
          
      </div>
    </div>
  </div>
</template>

<script setup>
import Sidebar from '../components/Layout/Sidebar.vue'
import { DockviewVue } from 'dockview-vue'
import 'dockview-vue/dist/styles/dockview.css'
import { themeLightSpaced } from 'dockview-vue'

import { setDockviewApi, getDockviewApi } from '../dockviewApi'

import WatermarkPanel from '../components/Layout/WatermarkPanel.vue'
import AddButton from '../components/Layout/AddButton.vue'

import Gantt from '../components/TimeSystem/Gantt.vue'
import Calendar from '../components/TimeSystem/Calendar/Calendar.vue'
import ToDo from '../components/TimeSystem/ToDo/ToDo.vue'
import StatePlanning from '../components/PlanningSystem/StatePlanning.vue'

import { useRoute, useRouter } from 'vue-router'
import { watch, ref, computed, onMounted } from 'vue';
import { Breadcrumbs } from 'frappe-ui'

import { House, LayoutPanelTop } from 'lucide-vue-next'

const components = ["Gantt", "Calendar", "ToDo", "StatePlanning"]
const route = useRoute()
const router = useRouter()

const isInComponents = computed(() =>{
  if (components.includes(route.name) || route.name === "HomeIndex"){
    return true
  }
}
)

//Breadcrumbs
const breadcrumbItems = [
  {
    label: 'Home',
    icon: House,
    onClick: () => {
      router.push('/')
    },
  },
  {
    label: 'Workspace',
    icon: LayoutPanelTop,
    onClick: () => {
      router.push('/')
    },
  },
]


//Docking
defineOptions({
  components: {
    'dockview-vue': DockviewVue,
    watermarkComponent: WatermarkPanel,
    AddButton: AddButton,
    Gantt: Gantt,
    Calendar: Calendar,
    ToDo: ToDo,
    StatePlanning: StatePlanning
  },
})


const panels = ref([])
const dockviewReady = ref(false)


function onReady(event) {
  const eventApi = event.api
  setDockviewApi(eventApi)
  dockviewReady.value = true

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
      if (!panels.value.includes(route.name) && !(route.name === "HomeIndex")){
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
    if (!isInComponents.value) return
    if (!dockviewReady.value) return

    const api = getDockviewApi()
    panels.value = Object.values(api.panels).map(p => p.id)

    if (!panels.value.includes(name) && !(route.name === "HomeIndex")) {
      api.addPanel({ id: name, component: name })
    }
  }
)



function close() {
  localStorage.clear()
}




import { useToast } from "vue-toastification";
import { Alert } from 'frappe-ui'
import { emitter } from '../event-bus';


emitter.on('toast',  (data)=>{
  const toast = useToast();
  const id = toast(
    {
      component: Alert,
      props: {
        title: data.title,
        description: data.description,
        theme: data.theme,
      },
      listeners: {
        close: () => toast.dismiss(id),
      },
    },
    {
      type: "default",
      toastClassName: "toast-reset",
      bodyClassName: "p-0",
      hideProgressBar: true,
      closeButton: false,
      closeOnClick: false,
    }
  )
})

</script>
<style>
.toast-reset {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  border-radius: 0 !important;
}

.Vue-Toastification__toast--default {
  background: transparent !important;
  box-shadow: none !important;
}
.toast-reset svg.lucide.lucide-x {
  color: #000 !important;
}
.Vue-Toastification__icon {
  display: none !important;
}
</style>
