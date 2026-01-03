<template>
<div class="relative h-full overflow-hidden p-5">
  <Calendar
    v-show="notLoading"
    class="h-full"
    :config="{
      defaultMode: viewMode,
      isEditMode: true,
      allowCustomClickEvents: true,
      enableShortcuts: false,
    }"
    :events="events"

    @update="(event) => sendUpdate(event)"
    @click="(event) => console.log(event)"
    @dblClick="(event) => handleDoubleClick(event)"
    @cellClick="(data) => handleCellClick(data)"
  />

  <LoadingText
    v-if="!notLoading"
    text="Loading Events..."
    class="absolute inset-0 flex items-center justify-center text-5xl scale-150"
  />
  <div>
    <EditEventForm v-model:show="showEditForm" :event="sendEvent"/>
    <NewEventForm v-model:show="showNewForm" :data="sendData"/>
  </div>
</div>
</template>
<script setup>
import { Calendar, createResource, createDocumentResource, LoadingText } from 'frappe-ui';
import {ref, watch, computed, nextTick, reactive, shallowRef } from 'vue'
import EditEventForm from './EditEventForm.vue';
import NewEventForm from './NewEventForm.vue';
import {getDockviewApi} from '../../../dockviewApi'

const api = shallowRef(null)
const panel = shallowRef(null)

onMounted(async () => {
  await nextTick()          
  api.value = getDockviewApi()
  panel.value = api?.value.getPanel('Gantt')
})



const viewMode = ref('Month')
const notLoading = ref(true)
const showEditForm = ref(false)
const showNewForm = ref(false)

viewMode.value = localStorage.getItem('calendar_view')


let sendEvent = {}
let sendData = {}

function handleDoubleClick(event){
  showEditForm.value = true
  sendEvent = event
}

function handleCellClick(data){
  showNewForm.value = true
  sendData = data

}

//Load Events
const events = ref([])

//Load Month
const calendarActions = createResource({
  url: '/api/method/kratium.api.get_final_action_list',
  params: {
    view_mode: 'Month',
    calendar: true,
  },
})

//Load Daily
let dailyActions = createResource({
url: '/api/method/kratium.api.get_final_action_list',
params:{
  view_mode: "Day",
  calendar: true
},
})

async function setEvents(){
  if (viewMode.value === "Month"){
    notLoading.value = false
    await calendarActions.fetch()
    events.value = calendarActions.data
    notLoading.value = true
  }
  else{
    notLoading.value = false
    await dailyActions.fetch()
    events.value = dailyActions.data
    notLoading.value = true
  }
  //Listen for event update submit
  emitter.on('event-update', async () => {
      if (viewMode.value === 'Month'){
        await calendarActions.fetch()
        events.value = calendarActions.data
        emitter.emit('event-updated')
      }
      else{
        await dailyActions.fetch()
        events.value = dailyActions.data
        emitter.emit('event-updated')
      }
  })
}
setEvents()

// update sync
async function sendUpdate(event) {
  const url = `/api/v2/document/Action/${event.id}`
  const payload = {
    id: event.id,
    action_name: event.title,
    start_date: event.fromDateTime,
    end_date: event.toDateTime,
    color: event.color,
    full_day: event.isFullDay,
  }
  

  const res = await fetch(url, {
    method: 'PUT', 
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    credentials: 'include', 
  })
  emitter.emit('event-updated')
}



//Listen for viewmode change easier than creating my own header
import { onMounted, onBeforeUnmount } from 'vue'
import { emitter } from '../../../event-bus';

let observer

function setupCalendarObserver() {
  observer?.disconnect()

  const container = document.querySelector('[role="radiogroup"]')
  if (!container) return

  observer = new MutationObserver(() => {
    const active = container.querySelector('[aria-checked="true"]')
    if (!active) return

    const mode = active.textContent.trim()
    onModeChange(mode)
    
  })

  observer.observe(container, {
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-checked'],
  })
}



onBeforeUnmount(() => {
  observer?.disconnect()
})

onMounted(async () => {
  await nextTick()
  setupCalendarObserver()
})

watch(notLoading, async (v) => {
  if (v) {
    await nextTick()
    setupCalendarObserver()
  }
})
//End observer


onBeforeUnmount(() => {
  observer?.disconnect()
})







async function onModeChange(mode) {
  localStorage.setItem('calendar_view', mode)
  if (mode === 'Day' || mode === 'Week') {
      notLoading.value = false
      await dailyActions.fetch()
      events.value = dailyActions.data
      viewMode.value = mode
      notLoading.value = true
  }
    else{
        notLoading.value = false
        await calendarActions.fetch()
        events.value = calendarActions.data
        viewMode.value = mode
        notLoading.value = true
  }
}


emitter.on('todo-updated', ()=>{
  if (!(api.value.getPanel('Calendar') === undefined) && !(viewMode === 'Month')){  
    onModeChange(viewMode.value)
  }
})

</script>

