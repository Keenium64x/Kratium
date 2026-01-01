<template >
    <div class="flex-col space-y-6 p-4 overflow-auto">
        <FormControl 
        type="text"
        size="sm"
        variant="subtle"
        placeholder="John Doe"
        label="Todo Name"


        style="margin: 1 !important;"
        />
        <Textarea
        :variant="'subtle'"
        size="sm"
        placeholder="Placeholder"
        :modelValue="todoName"
        label="Label"
        v-bind="todoNameAttrs"      
        
        style="margin: 1 !important;"        
      />  
        <ErrorMessage :message="errors.todoName" class="!my-4" />
        <pre>{{ api?.panels }}</pre>
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource, TimePicker, Dialog, FormControl, DateTimePicker, Button, Textarea } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../../event-bus'
import { Trash2 } from 'lucide-vue-next'
import { getDockviewApi } from '../../dockviewApi'


const show = defineModel('show')
const data = defineModel('data')
const isInvalidForm = ref(false)

//Loading
import { shallowRef, onMounted, nextTick } from 'vue'

const api = shallowRef(null)

onMounted(async () => {
  await nextTick()          // let vee-validate settle
  api.value = getDockviewApi()
})



//Validation
const editFormSchema = yup.object({
  todoName: yup.string().required().label("todo Name"),

})

const { values, meta, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});

const [todoName, todoNameAttrs] = defineField('todoName')



let updatetodo = null

watch(data, (val) => {
  if (!val || !val.start_date || !val.end_date) return
  const startDate = val.start_date.split(" ")[0]
  const startTime = val.start_date.split(" ")[1]

  const endDate = val.end_date.split(" ")[0]
  const endTime = val.end_date.split(" ")[1]
    
  setValues({
    todoName: val.action_name,
    todoStartDate: startDate,
    todoEndDate: endDate,
    todoStartTime: startTime,
    todoEndTime: endTime,
    todoColor: val.color,
    todoDuration: val.estimated_hours,
    todoReminder: val.reminder
  })


  if (!updatetodo) {
    updatetodo = createDocumentResource({
      doctype: 'Action',
      name: val.name, 
    })
  }
}, { immediate: true })


async function editOnSucess(values, { resetForm }) {
 
}

function editOnFail(){
   
}

const onSubmit = handleSubmit(editOnSucess, editOnFail)


async function onDelete(){
     
}


</script>
