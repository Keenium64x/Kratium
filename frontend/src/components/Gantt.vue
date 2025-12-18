<template>
  <div class="flex-col">
    <div class="flex justify-center gap-x-4 mt-6 mb-4">
      <Button
      :variant="'outline'"
      theme="gray"
      size="lg"
      label="Yearly"
      tooltip="Set To Yearly"
      @click="setYear"
    >
      Yearly
    </Button>
      <Button
      :variant="'outline'"
      theme="gray"
      size="lg"
      label="Monthly"
      tooltip="Set To Monthly"
      @click="setMonth"
    >
      Monthly
    </Button>
      <Button
      :variant="'outline'"
      theme="gray"
      size="lg"
      label="Daily"
      tooltip="Set To Daily"
      @click="setDay"
    >
      Daily
    </Button>
  </div>
<div :style="{ height: ganttHeight + 'px' }" class="mt-0">
  <div
    id="gantt"
    v-show="!ganttLoading"
    class=" h-full m-10 rounded-xl border mt-2"
  ></div>

  <div
    v-if="ganttLoading"
    class="flex items-center justify-center pointer-events-none"
  >
    <LoadingText class="text-5xl scale-150" />
  </div>
</div>
  </div>
</template>

<script setup>
import { createResource, LoadingText, Button } from 'frappe-ui'
import { watch, ref, computed, onMounted, } from 'vue'

const ganttLoading = ref(true)

let view = ref("Month")
const setDay = () => {
  view.value = "Day"
}
const setMonth = () => {
  view.value = "Month"
}
const setYear = () => {
  view.value = "Year"
}




watch(view, async () => {
  updateGantt()
})

let gantt = null
const ganttHeight = 600

onMounted(()=>{
    let final_actions_initial = createResource({
  url: '/api/method/kratium.api.get_final_action_list',
  params:{
    view_mode: view.value
  }
})
  ganttLoading.value = true
  final_actions_initial.fetch().then(() => {
    ganttLoading.value = false
    const data = final_actions_initial.data
    if (!data) return

    const tasks = data.map((a, i) => ({
      id: String(i + 1),
      name: a.id,
      start: a.start,
      end: a.end,
      progress: 0,
    }))

    gantt = new Gantt('#gantt', tasks, {
      container_height: ganttHeight,
      view_mode: view.value,
      readonly: true
    })
})
})






function updateGantt(){
    let final_actions_refresh = createResource({
  url: '/api/method/kratium.api.get_final_action_list',
  params:{
    view_mode: view.value
  }
})
  ganttLoading.value = true
  final_actions_refresh.fetch().then(() => {
    ganttLoading.value = false
    const data = final_actions_refresh.data
    if (!data || !gantt) return

    const tasks = data.map((a, i) => ({
      id: String(i + 1),
      name: a.id,
      start: a.start,
      end: a.end,
      progress: 0,
    }))

    gantt.refresh(tasks)
    gantt.change_view_mode(view.value)

})}

</script>



