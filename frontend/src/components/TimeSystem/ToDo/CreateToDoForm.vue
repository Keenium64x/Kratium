<template>
  <div>
    <Dialog 
    :options="{
        title: 'Create New ToDo',
        actions: [
        {
        label: 'Create',
        variant: 'solid',
        onClick: () => onSubmit(),
        },
    ],
    }"
    v-model="show"
    
    
    >
    <template #body-content>
        <div class="flex-col space-y-6 ">
            <FormControl 
            type="text"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Event Name"
            v-model="ToDoName"
            v-bind="ToDoNameAttrs"
            style="margin: 1 !important;"
            />
            <ErrorMessage :message="errors.ToDoName" class="!my-4" />


            
            <ErrorMessage :message="errors.eventColor" class="!my-4" />
            <Alert
            title="Form Invalid"
            description="The Details you have entered are Incorrect"
            theme="red"
            v-model="isInvalidForm"
          />            
          <pre>{{ errors }}</pre>
        </div>
    </template>
    </Dialog>
  </div>
</template>
<script setup>
import { ListView, Dialog, ErrorMessage, createDocumentResource } from 'frappe-ui';
import { ref, watch}  from 'vue'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    

const show = defineModel('show')
const isInvalidForm = ref(false)

//Validation
const editFormSchema = yup.object({
  ToDoName: yup.string().required().label("Event Name"),

})

//Create Form Validator
const { values, meta, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});
const [ToDoName, ToDoNameAttrs] = defineField('ToDoName')

//Submission



async function editOnSucess(values, { resetForm }) {
  if (!updateEvent) return

  await createTodo.setValue.submit({
    name1: values.eventName,
    start_date: values.eventStartDate + " " + values.eventStartTime,
    end_date: values.eventEndDate + " " + values.eventEndTime,
    color: values.eventColor,
    full_day: values.eventFullDay,
  })

  resetForm()
  show.value = false
  emitter.emit('event-update')
}

function editOnFail(){
  isInvalidForm.value = true
}

const onSubmit = handleSubmit(editOnSucess, editOnFail)


watch(errors, ()=>{
  if (!meta.valid){
    isInvalidForm.value = false
  }
})


</script>
