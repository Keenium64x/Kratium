<template>
    <div>
    <Dialog v-model="show" >
    <template #body-title>
      <div class="flex justify-between items-center w-full">
        <h3 class="text-2xl font-semibold">
          Edit Todo
        </h3>
        <Trash2 :size="20" class="m-1 pt-1 cursor-pointer text-red-500" @click="onDelete" />
      </div>
    </template>

    <template #body-content>
        <div class="flex-col space-y-6 ">
            <FormControl 
            type="text"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Todo Name"
            v-model="todoName"
            v-bind="todoNameAttrs"
            style="margin: 1 !important;"
            />
            <ErrorMessage :message="errors.todoName" class="!my-4" />


            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="date"
            label="Start Date"
            v-model="todoStartDate"
            v-bind="todoStartDateAttrs"
            />
            <ErrorMessage :message="errors.todoStartDate" class="!my-4" />
            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="End Date"
            v-model="todoEndDate"
            v-bind="todoEndDateAttrs"
            />
            <ErrorMessage :message="errors.todoEndDate" class="!my-4" />

            <p class="block text-xs text-ink-gray-5 !mt-6">Start Time</p>
            <TimePicker
            class="!my-2"
            v-model="todoStartTime"
            v-bind="todoStartTimeAttrs"
            variant="subtle"
            :interval="15"
            :allowCustom="true"
            :autoClose="true"
            :use12Hour="false"
            placement="bottom-start"
            placeholder="Start Time"
            scrollMode="center"
            />
            <ErrorMessage :message="errors.todoStartTime" class="!my-4" />

            <p class="block text-xs text-ink-gray-5 !mt-6">End Time</p>
            <TimePicker
            class="!my-2"
            v-model="todoEndTime"
            v-bind="todoEndTimeAttrs"
            variant="subtle"
            :interval="15"
            :allowCustom="true"
            :autoClose="true"
            :use12Hour="false"
            placement="bottom-start"
            placeholder="End Time"
            scrollMode="center"
            />            
            <ErrorMessage :message="errors.todoEndTime" class="!my-4" />

            <p class="block text-xs text-ink-gray-5 !mt-6">Reminder At</p>
            <DateTimePicker
            v-model="todoReminder"
            v-bind="todoReminderAttrs"
            variant="subtle"
            label="Reminder Date"
            class="!my-2"
            />

            <FormControl 
            type="number"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Duration"
            v-model="todoDuration"
            v-bind="todoDurationAttrs"
            style="margin: 1 !important;"
            />
            <ErrorMessage :message="errors.todoDuration" class="!my-4" />

            <FormControl 
            type="select"
            :options="[
            {
                label: 'amber',
                value: 'amber',
            },
            {
                label: 'violet',
                value: 'violet',
            },
            {
                label: 'pink',
                value: 'pink',
            },
            {
                label: 'cyan',
                value: 'cyan',
            },
            {
                label: 'blue',
                value: 'blue',
            },
            {
                label: 'orange',
                value: 'orange',
            },
                        {
                label: 'green',
                value: 'green',
            },
            ]"
            size="sm"
            variant="subtle"
            label="Color"
            v-model="todoColor"
            v-bind="todoColorAttrs"
            />
            <ErrorMessage :message="errors.todoColor" class="!my-4" />
            <Alert
            title="Form Invalid"
            description="The Details you have entered are Incorrect"
            theme="red"
            v-model="isInvalidForm"
          />
        </div>
    </template>

  <template #actions="{ close }">
    <div class="flex justify-start flex-row-reverse gap-2">
      <Button
        variant="subtle"
        theme="green"
        @click="onSubmit()"
      >
        Save Changes
      </Button>
      <Button
        variant="outline"
        @click="show = false"
      >
        Cancel
      </Button>
      <Button
        variant="subtle"
        theme="red"
        @click="onDelete()"
      >
        Delete
      </Button>      
    </div>
  </template>


    </Dialog>
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource, TimePicker, Dialog, FormControl, DateTimePicker } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../../../event-bus'
import { Trash2 } from 'lucide-vue-next'

const show = defineModel('show')
const data = defineModel('data')
const isInvalidForm = ref(false)


const editFormSchema = yup.object({
  todoName: yup.string().required().label("todo Name"),
  todoColor: yup.string().label("Color"),

  todoStartDate: yup
    .date()
    .nullable()
    .typeError("Start Date is required")
    .required("Start Date is required"),

  todoEndDate: yup
    .date()
    .nullable()
    .typeError("End Date is required")
    .required("End Date is required")
    .min(yup.ref("todoStartDate"), "End Date cannot be before Start Date"),

  todoStartTime: yup.string().required().label("Start Time"),
  todoEndTime: yup
    .string()
    .required()
    .test(
      "end-after-start",
      "End time cannot be before start time",
      function (endTime) {
        const {
          todoStartDate,
          todoEndDate,
          todoStartTime,
        } = this.parent

        if (
          !todoStartDate ||
          !todoEndDate ||
          !todoStartTime ||
          !endTime
        ) {
          return true
        }

        const startDate = new Date(todoStartDate)
        const endDate = new Date(todoEndDate)

        const [sh, sm] = todoStartTime.split(":").map(Number)
        const [eh, em] = endTime.split(":").map(Number)

        const start = new Date(startDate)
        start.setHours(sh, sm, 0, 0)

        const end = new Date(endDate)
        end.setHours(eh, em, 0, 0)

        return end.getTime() >= start.getTime()
      }
    )
    .label("End Time"),

  todoDuration: yup
    .number()
    .typeError("Duration must be a number")
    .min(1, "Duration must be greater than 0")
    .required("Duration is required"),

  todoReminder: yup.string().nullable().notRequired().label("Reminder At")
})

const { values, meta, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});

const [todoName, todoNameAttrs] = defineField('todoName')
const [todoStartDate, todoStartDateAttrs] = defineField('todoStartDate')
const [todoEndDate, todoEndDateAttrs] = defineField('todoEndDate')
const [todoStartTime, todoStartTimeAttrs] = defineField('todoStartTime')
const [todoEndTime, todoEndTimeAttrs] = defineField('todoEndTime')
const [todoDuration, todoDurationAttrs] = defineField('todoDuration')
const [todoReminder, todoReminderAttrs] = defineField('todoReminder')
const [todoColor, todoColorAttrs] = defineField('todoColor')


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
  if (!updatetodo) return

  await updatetodo.setValue.submit({
    action_name: values.todoName,
    start_date: values.todoStartDate + " " + values.todoStartTime,
    end_date: values.todoEndDate + " " + values.todoEndTime,
    estimated_hours: values.todoDuration,
    color: values.todoColor,
  })
  resetForm()
  show.value = false
  emitter.emit('todo-update')

  emitter.emit('toast', {
  title: "Todo Updated",
  description: "",
  theme: "green"
})      
}

function editOnFail(){
  isInvalidForm.value = true
  emitter.emit('toast', {
  title: "Form Invalid",
  description: "",
  theme: "red"
})        
}

const onSubmit = handleSubmit(editOnSucess, editOnFail)


async function onDelete(){
  if (!updatetodo) return  
  updatetodo.delete.submit(data.name)
  show.value = false
  emitter.emit('todo-update')
  emitter.emit('toast', {
  title: "Todo Deleted",
  description: "",
  theme: "green"
})        
}

watch(errors, ()=>{
  if (!meta.valid){
    isInvalidForm.value = false
  }
})


watch(
  () => values.todoStartDate,
  (newVal) => {
    if (!newVal) return
    setValues({
      todoEndDate: newVal,
    })
  }
)



</script>