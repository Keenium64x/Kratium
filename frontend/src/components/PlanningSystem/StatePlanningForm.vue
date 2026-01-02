<template >
    <div class="flex-col space-y-6 p-4 overflow-auto">
        <FormControl 
        type="text"
        size="sm"
        variant="subtle"
        placeholder="John Doe"
        label="Goal Name"
        :modelValue="GoalName"
        v-bind="GoalNameAttrs"  

        style="margin: 1 !important;"
        />
        <Textarea
        :variant="'subtle'"
        size="sm"
        placeholder="Placeholder"
        :modelValue="witg"
        v-bind="witggAttrs"      
        label="What is the Goal?"
        style="margin: 1 !important;"        
      />  
        <ErrorMessage :message="errors.GoalName" class="!my-4" />

        <TextEditor
        editor-class="prose prose-sm min-w-full min-h-[10rem] border rounded-b-lg border-t-0 p-3"
        :content="witnotg"
        placeholder="Type something..."
        :bubbleMenu="true"
        :fixed-menu="true"   
        v-bind="witnotgAttrs"
        v-model="witnotg"

        @change="(val) => console.log(witnotg)"
        />

        <div>{{ witnotg }}</div>
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource, TimePicker, Dialog, FormControl, DateTimePicker, Button, Textarea, TextEditor } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../../event-bus'
import { Trash2 } from 'lucide-vue-next'
import { getDockviewApi } from '../../dockviewApi'


const show = defineModel('show')
const data = defineModel('data')
const isInvalidForm = ref(false)
const Goal = ref('')
const textReady = ref('')

//Loading
import { shallowRef, onMounted, nextTick } from 'vue'

const api = shallowRef(null)
const panel = shallowRef(null)
  
function toACT(id) {
  const parts = id.split('-')
  if (parts.length < 3) return id
  parts[1] = 'ACT'
  return parts.join('-')
}

onMounted(async () => {
  await nextTick()          
  api.value = getDockviewApi()
  panel.value = api?.value.getPanel('StatePlanningForm')

})

watch(()=>panel.value, (panel)=>{
  let stateGoal = createDocumentResource({
    doctype: 'Action',
    name: panel.params.id,
  })
  stateGoal.get.promise.then(()=>{
    Goal.value = stateGoal.get.data
  })
})


emitter.on('goal-open-node', (data) => {
  let updateStateGoal = createDocumentResource({
    doctype: 'Action',
    name: data.id,
  })  
  updateStateGoal.get.promise.then(()=>{
    Goal.value = updateStateGoal.get.data
  })  
})




//Validation
const editFormSchema = yup.object({
  GoalName: yup.string().required().label("Goal Name"),
  
})

const { values, meta, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});

const [GoalName, GoalNameAttrs] = defineField('GoalName')
const [witg, witggAttrs] = defineField('witg')
const [witnotg, witnotgAttrs] = defineField('witnotg')
const [wfwis, wfwisAttrs] = defineField('wfwis')
const [dihtk, dihtkAttrs] = defineField('dihtk')
const [witkin, witkinAttrs] = defineField('witwitkinnotg')
const [hciotkn, hciotknAttrs] = defineField('hciotkn')
const [wats, watsAttrs] = defineField('wats')
const [watba, watbaAttrs] = defineField('watba')

watch(()=>Goal.value, (val) => {

  setValues({
    GoalName: val.action_name,
    witnotg: val.witnotg
  })


})


async function editOnSucess(values, { resetForm }) {
 
}

function editOnFail(){
   
}

const onSubmit = handleSubmit(editOnSucess, editOnFail)


async function onDelete(){
     
}


</script>
