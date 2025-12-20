<template>
<div class="flex h-screen flex-col overflow-hidden p-5">
  <Calendar
  style="z-index: 0;"
    :config="{
      defaultMode: 'Month',
      isEditMode: true,
      eventIcons: {
      },
      allowCustomClickEvents: true,
      enableShortcuts: false,
      
    }"
    :events="events"
    @click="(event) => console.log('onClick', event)"
    @dblClick="(event) => handleDoubleClick(event)"
    @cellClick="(data) => handleCellClick(data)"
    @update="(event) => sendUpdate(event)"    
  />


  <div>
    <EditEventForm v-model:show="showEditForm" :event="sendEvent"/>
    <NewEventForm v-model:show="showNewForm" :data="sendData"/>
  </div>
    
</div>
</template>
<script setup>
import { Calendar, createResource, createDocumentResource } from 'frappe-ui';
import {ref, watch, computed, nextTick, reactive } from 'vue'
import EditEventForm from './EditEventForm.vue';
import NewEventForm from './NewEventForm.vue';

const showEditForm = ref(false)
const showNewForm = ref(false)
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

const calendarActions = createResource({
  url: '/api/method/kratium.api.get_final_action_list',
  params: {
    view_mode: 'Month',
    calendar: true,
  },
})

calendarActions.fetch().then(()=>{
  events.value = calendarActions.data
})
//Listen for event update submit
emitter.on('event-update', async () => {
    await calendarActions.fetch()
    events.value = calendarActions.data
})

let updateEventfunc = createDocumentResource({
doctype: 'Action',
name: "Event", 
})

console.log(updateEventfunc.doc)

//update sync
async function sendUpdate(event){
  updateEventfunc.update({
    doctype: '',
    name: ''
  })

  updateEventfunc.setValue.submit({
  name1: event.title,
  start_date: event.fromDateTime,
  end_date: event.toDateTime,
  color: event.color,
  full_day: event.isFullDay,
})    


}



//Listen for viewmode change easier than creating my own header
import { onMounted, onBeforeUnmount } from 'vue'
import { emitter } from '../event-bus';

let observer

onMounted(() => {
  const container = document.querySelector('[role="radiogroup"]')
  if (!container) return

  observer = new MutationObserver(() => {
    const active = container.querySelector('[role="radio"][aria-checked="true"] button')
    if (!active) return

    const value = active.getAttribute('value')
    onModeChange(value)
  })

  observer.observe(container, {
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-checked']
  })
})

onBeforeUnmount(() => {
  observer?.disconnect()
})

function onModeChange(mode) {
  let final_actions_refresh = createResource({
  url: '/api/method/kratium.api.get_final_action_list',
  params:{
    view_mode: "Day",
    calendar: false
  }
})
}

</script>

