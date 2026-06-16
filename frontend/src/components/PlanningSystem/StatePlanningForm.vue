<template >
    <div class="flex-col justify-center space-y-6 p-4 h-full w-full overflow-auto">

      <div class="m-4" v-if="activeStep != 4">
        <Stepper class="flex w-full items-start gap-2" v-model="activeStep">
          <StepperItem
            v-for="step in steps"
            :key="step.step"
            v-slot="{ state }"
            class="relative flex w-full flex-col items-center justify-center"
            :step="step.step"
          >
            <StepperSeparator
              v-if="step.step !== steps[steps.length - 1]?.step"
              class="absolute left-[calc(50%+20px)] right-[calc(-50%+10px)] top-5 block h-0.5 shrink-0 rounded-full bg-muted group-data-[state=completed]:bg-primary"
            />
            <StepperTrigger as-child>
              <div class="pointer-events-none select-none">
                <Button
                  :variant="state === 'completed' || state === 'active' ? 'default' : 'outline'"
                  size="icon"
                  class="z-10 rounded-full shrink-0"
                  :class="[state === 'active' && 'ring-2 ring-ring ring-offset-2 ring-offset-background']"
                >
                  <Check v-if="state === 'completed' && !(step.step === 2 && !dihtk)" class="size-5" />
                  <Hourglass v-if="state === 'completed' && (step.step === 2 && !dihtk)" class="size-5"  />
                  <Circle v-if="state === 'active'" />
                  <Dot v-if="state === 'inactive'" />
                </Button>
              </div>
            </StepperTrigger>
            <div class="mt-5 flex flex-col items-center text-center">
              <StepperTitle
                :class="[state === 'active' && 'text-primary']"
                class="text-sm font-semibold transition lg:text-base"
              >
                {{ step.title }}
              </StepperTitle>
              <StepperDescription
                :class="[state === 'active' && 'text-primary']"
                class="sr-only text-xs text-muted-foreground transition md:not-sr-only lg:text-sm"
              >
                {{ step.description }}
              </StepperDescription>
            </div>
          </StepperItem>
        </Stepper>      
      </div>
        <div v-if="activeStep === 1">
          <FormControl 
          type="text"
          size="sm"
          variant="subtle"
          placeholder="Enter Name..."
          label="Goal Name"
          v-model="GoalName"
          v-bind="GoalNameAttrs"  

          style="margin: 1 !important;"
          />
          <ErrorMessage :message="errors.GoalName" class="!my-4" />
        </div>

        <div v-if="activeStep === 1">
          <Textarea
          aria-label="IDC"
          :variant="'subtle'"
          size="sm"
          placeholder="Placeholder"
          :modelValue="witg"
          v-bind="witggAttrs"      
          label="What is the Goal?"
          style="margin: 1 !important;"        
          />  
        </div>

        <div v-if="activeStep === 1">
          <p class="block text-xs text-ink-gray-5 !mt-6">What is the nature of the Goal?</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="witnotg"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="witnotgAttrs"
          v-model="witnotg"
          />
        </div>        
        
        <div v-if="activeStep === 1">
          <p class="block text-xs text-ink-gray-5 !mt-6">Time Range</p>
          <DateRangePicker
            v-model="dateRangeValue"
            variant="subtle"
            placeholder="Date Filter"
            class="w-full !my-2"
          />
          <ErrorMessage :message="errors.end_date" class="!my-4" />
        </div>
   

        <div v-if="activeStep === 2">
          <p class="block text-xs text-ink-gray-5 !mt-6">Warent for what is needed?</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="wfwis"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="wfwisAttrs"
          v-model="wfwis"
          />
        </div>

        <div v-if="activeStep === 2">
          <FormControl 
          type="checkbox"
          size="sm"
          variant="subtle"
          label="Do I have the Knowledge?"
          v-model="dihtk"
          v-bind="dihtkAttrs"  

          style="margin: 1 !important;"
          />
          <ErrorMessage :message="errors.dihtk" class="!my-4" />          
        </div>

        <div v-if="activeStep === 3 && dihtk === false">
          <p class="block text-xs text-ink-gray-5 !mt-6">What is the Knowledge I need?</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="witkin"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="witkinAttrs"
          v-model="witkin"
          />
        </div>        

        <div v-if="activeStep === 3 && dihtk === false">
          <p class="block text-xs text-ink-gray-5 !mt-6">How can I obtain the Knowledge needed?</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="hciotkn"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="hciotknAttrs"
          v-model="hciotkn"
          />
        </div>

        <div v-if="activeStep === 3 && dihtk === true">
          <p class="block text-xs text-ink-gray-5 !mt-6">What are the States?</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="wats"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="watsAttrs"
          v-model="wats"
          />
        </div>        

        <div v-if="activeStep === 3 && dihtk === true">
          <p class="block text-xs text-ink-gray-5 !mt-6">What are the Bridging Actions</p>
          <TextEditor
          aria-label="IDC"
          class="!my-2"
          editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
          :content="watba"
          placeholder="Type something..."
          :bubbleMenu="true"
          :fixed-menu="true"   
          v-bind="watbaAttrs"
          v-model="watba"
          />
        </div>

        <div
          v-if="activeStep != 4"
          class="flex w-full gap-4 items-center justify-between flex-wrap"
        >
          <FrappeButton
            class="flex-shrink-0 order-1"
            :variant="'outline'"
            theme="gray"
            size="lg"
            @click="prevStep"
          >
            Back
          </FrappeButton>

          <div
            class="flex flex-1 min-w-0 gap-4
                  justify-center
                  flex-row flex-wrap
                  order-2"
          >
            <div class="flex gap-2 flex-wrap justify-center w-full sm:w-auto !items-center">
              <FrappeButton
                class="min-w-[120px] flex-shrink-0"
                :variant="'outline'"
                theme="gray"
                size="md"
                @click="onClose"
              >
                Cancel
              </FrappeButton>

              <FrappeButton
                class="min-w-[120px] flex-shrink-0"
                :variant="'subtle'"
                theme="red"
                size="md"
                @click="onDelete"
              >
                Delete
              </FrappeButton>
            </div>

            <div class="flex justify-center w-full sm:w-auto">
            <Popover>
              <template #target="{ togglePopover }">
                    <FrappeButton
                      class="flex-shrink-0 !rounded-full"
                      :variant="'solid'"
                      theme="gray"
                      size="xl"
                      @click="togglePopover"
                    >
                      <Plus />
                    </FrappeButton>
              </template>    
              <template #body-main>
                <div >
                  <div v-if="!enterNameCon" class="flex flex-col space-y-2 p-2 text-ink-gray-9">
                    <Button
                    :variant="'outline'"
                    size="lg"
                    @click.stop="enterName('custom')"
                    >
                    ▲ State Goal
                    </Button>
                    <Button
                    :variant="'outline'"
                    size="lg"
                    @click.stop="enterName('cusout')"
                    >
                    ■  Base Goal
                    </Button>    
                  </div>  
                  <div v-if="enterNameCon" class="p-4">
                      <FormControl
                        :type="'text'"
                        size="lg"
                        variant="subtle"
                        placeholder="Finish Studies"
                        label="Enter Name"
                        v-model="NameInput"
                        @keydown.enter.prevent="onAdd()"
                      />
                  </div>      
                </div>
              </template>  
            </Popover>  
            </div>

            <div class="flex gap-2 flex-wrap justify-center w-full sm:w-auto items-center">
              <FrappeButton
                class="min-w-[120px] flex-shrink-0"
                :variant="'subtle'"
                theme="blue"
                size="md"
              >
                Repo
              </FrappeButton>

              <FrappeButton
                class="min-w-[120px] flex-shrink-0"
                :variant="'subtle'"
                theme="green"
                size="md"
                @click="onSubmit"
              >
                Save
              </FrappeButton>
            </div>
          </div>

          <FrappeButton
            class="flex-shrink-0 order-3"
            :variant="'solid'"
            theme="gray"
            size="md"
            @click="nextStep"
          >
            {{ activeStep != 3 ? 'Next' : 'Submit' }}
          </FrappeButton>
        </div>
      <div class="flex items-center justify-center w-full" v-if="activeStep === 4">
        <DotLottieVue
          class="h-[500px] w-[500px]"
          autoplay
          loop
          src="/Checkmark.lottie"
        />
      </div>
      <DeleteConfirmDialog v-model:show="showDelete" />
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource, TimePicker, DateRangePicker, FormControl, DateTimePicker, Textarea, TextEditor, Popover } from 'frappe-ui'
import { Button as FrappeButton } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../../event-bus'
import { Hourglass, Plus, Trash2 } from 'lucide-vue-next'
import { getDockviewApi } from '../../dockviewApi'
import { DotLottieVue } from '@lottiefiles/dotlottie-vue'
import DeleteConfirmDialog from './DeleteConfirmDialog.vue'


const sleep = ms =>
  new Promise(resolve => setTimeout(resolve, ms))

const activeStep = ref(1)

async function nextStep() {
  const { valid } = await validate()
  if (!valid) return
  if(activeStep.value === 3){
    activeStep.value = Math.min(activeStep.value + 1, steps.length + 1)
    onSubmit()
    console.log('trig')
    await sleep(700)
    panel.value.api.close()
  }
  else{
    activeStep.value = Math.min(activeStep.value + 1, steps.length + 1)
  }
}

function prevStep() {
  activeStep.value = Math.max(activeStep.value - 1, 1)
}

function onClose(){
  panel.value.api.close()
}


const show = defineModel('show')
const data = defineModel('data')
const isInvalidForm = ref(false)
const Goal = ref('')
const textReady = ref('')

//Loading
import { shallowRef, onMounted, nextTick } from 'vue'

const api = shallowRef(null)
const panel = shallowRef(null)
const statePanel = shallowRef(null)
const id = ref('')


onMounted(async () => {
  await nextTick()          
  api.value = getDockviewApi()
  panel.value = api?.value.getPanel('StatePlanningForm')
  statePanel.value = api?.value.getPanel('StatePlanning')

})

watch(()=>panel.value, (panel)=>{
  let stateGoal = createDocumentResource({
    doctype: 'Action',
    name: panel.params.id,
  })
  id.value = panel.params.id
  stateGoal.get.promise.then(()=>{
    Goal.value = stateGoal.get.data
  })
})


emitter.on('goal-open-node', (data) => {
  let updateStateGoal = createDocumentResource({
    doctype: 'Action',
    name: data.id,
  })  
  id.value = data.id
  updateStateGoal.get.promise.then(()=>{
    Goal.value = updateStateGoal.get.data
  })  
})




//Validation
const editFormSchema = yup.object({
  GoalName: yup.string().required().label("Goal Name"),

})

const {
  values,
  meta,
  errors,
  defineField,
  handleSubmit,
  setValues,
  validate
} = useForm({
  validationSchema: editFormSchema
})

const [GoalName, GoalNameAttrs] = defineField('GoalName')
const [witg, witggAttrs] = defineField('witg')
const [witnotg, witnotgAttrs] = defineField('witnotg')
const [wfwis, wfwisAttrs] = defineField('wfwis')
const [dihtk, dihtkAttrs] = defineField('dihtk')
const [witkin, witkinAttrs] = defineField('witwitkinnotg')
const [hciotkn, hciotknAttrs] = defineField('hciotkn')
const [wats, watsAttrs] = defineField('wats')
const [watba, watbaAttrs] = defineField('watba')

const [start_date, start_dateAttrs] = defineField('start_date')
const [end_date, end_dateAttrs] = defineField('end_date')
const [constraints, constraintsAttrs] = defineField('constraints')

const dateRangeValue = ref(null)

watch(()=>Goal.value, (val) => {
  setValues({
    GoalName: val.action_name,
    start_date: val.start_date,
    end_date: val.end_date,
    witg: val.witg,
    witnotg: val.witnotg,
    wfwis: val.wfwis,
    dihtk: val.dihtkm === '1'? true : false,
    witkin: val.witkin,
    hciotkn: val.hciotkn,
    wats: val.wats,
    watba: val.watba
  })

  function concatDates(startDate, endDate) {
    return `${startDate},${endDate}`
  }

  dateRangeValue.value = concatDates(val.start_date, val.end_date)

})


async function editOnSucess(val, { resetForm }) {
  let dupdateStateGoal = createDocumentResource({
    doctype: 'Action',
    name: id.value,
})

  await dupdateStateGoal.setValue.submit({
    action_name: val.GoalName,
    start_date: val.start_date,
    end_date: val.end_date,
    witg: val.witg,
    witnotg: val.witnotg,
    wfwis: val.wfwis,
    dihtk: val.dihtkm,
    witkin: val.witkin,
    hciotkn: val.hciotkn,
    wats: val.wats,
    watba: val.watba,
  })

  emitter.emit('goal-form-updated')     

  emitter.emit('toast', {
  title: `Goal ${val.GoalName} Updated`,
  description: "",
  theme: "green"
})     
}

function editOnFail(){

}

const onSubmit = handleSubmit(editOnSucess, editOnFail)



watch(() => dateRangeValue.value, (val) => {
  if (!val) return

  const [start_date, end_date] = val.split(',')

  setValues({
    start_date,
    end_date,
  })
})

const showDelete = ref(false)

function onDelete(){
  statePanel.value = api?.value.getPanel('StatePlanning')
  if (statePanel.value === undefined){
    show.value = true
    showDelete.value = true
  }
  else{
  emitter.emit('goal-form-delete') 
  }

}

emitter.on('goal-deleted', ()=>{
  panel.value.api.close()
})

emitter.on('goal-delete-selected', async ()=>{
  if (statePanel.value === undefined){
  // let tupdateStateGoal = createDocumentResource({
  //   doctype: 'Action',
  //   name: id.value,
  // })  
  // await tupdateStateGoal.delete.submit(id.value)  
  show.value = false
  panel.value.api.close()
  }
})


import { Check, Circle, Dot,  } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Stepper, StepperDescription, StepperItem, StepperSeparator, StepperTitle, StepperTrigger } from '@/components/ui/stepper'
const steps = [
  {
    step: 1,
    title: 'Details',
    description: 'Provide information about the state',
  },
  {
    step: 2,
    title: 'Knowledge',
    description: 'Provide knowledge about the state',
  },
  {
    step: 3,
    title: 'Execution',
    description: 'Declare Child States and Bridging Actions',
  },
]


emitter.on('goal-name-edit', ()=>{
  let tupdateStateGoal = createDocumentResource({
    doctype: 'Action',
    name: id.value,
  })  
  tupdateStateGoal.get.promise.then(()=>{
    Goal.value = tupdateStateGoal.get.data
  })    
})



//adding
const popover = ref(true)
const enterNameCon = ref(false)
const type = ref('custom')
const NameInput = ref('')

function enterName(nodeType){
  enterNameCon.value = true
  type.value = nodeType
}

function onAdd() {
  emitter.emit('goal-add-node', { parentId: id.value, type: type.value, name: NameInput.value })
  enterNameCon.value = false
}






</script>
<style scoped>
div[data-orientation="horizontal"][role="none"].absolute.h-0\.5 {
  top: 1.9rem !important;
}
</style>