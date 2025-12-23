<template>
    <div>
    <Dialog 
    :options="{
        title: 'Edit Event',
        actions: [
        {
        label: 'Submit',
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
            v-model="eventName"
            v-bind="eventNameAttrs"
            style="margin: 1 !important;"
            />
            <ErrorMessage :message="errors.eventName" class="!my-4" />

            <FormControl 
            type="text"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Person"
            v-model="eventPerson"
            v-bind="eventPersonAttrs"
            />
            <ErrorMessage :message="errors.eventPerson" class="!my-4" />

            <FormControl 
            type="text"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Event Venue"
            v-model="eventVenue"
            v-bind="eventVenueAttrs"
            />  

            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="date"
            label="Start Date"
            v-model="eventStartDate"
            v-bind="eventStartDateAttrs"
            />
            <ErrorMessage :message="errors.eventStartDate" class="!my-4" />
            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="End Date"
            v-model="eventEndDate"
            v-bind="eventEndDateAttrs"
            />
            <ErrorMessage :message="errors.eventEndDate" class="!my-4" />

            <p class="block text-xs text-ink-gray-5 !mt-6">Start Time</p>
            <TimePicker
            class="!my-4"
            v-model="eventStartTime"
            v-bind="eventStartTimeAttrs"
            variant="subtle"
            :interval="15"
            :allowCustom="true"
            :autoClose="true"
            :use12Hour="false"
            placement="bottom-start"
            placeholder="Start Time"
            scrollMode="center"
            />
            <ErrorMessage :message="errors.eventStartTime" class="!my-4" />

            <p class="block text-xs text-ink-gray-5 !mt-6">End Time</p>
            <TimePicker
            class="!my-4"
            v-model="eventEndTime"
            v-bind="eventEndTimeAttrs"
            variant="subtle"
            :interval="15"
            :allowCustom="true"
            :autoClose="true"
            :use12Hour="false"
            placement="bottom-start"
            placeholder="End Time"
            scrollMode="center"
            />            
            <ErrorMessage :message="errors.eventEndTime" class="!my-4" />

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
            v-model="eventColor"
            v-bind="eventColorAttrs"
            />
            <ErrorMessage :message="errors.eventColor" class="!my-4" />
            <Alert
            title="Form Invalid"
            description="The Details you have entered are Incorrect"
            theme="red"
            v-model="isInvalidForm"
          />
        </div>
    </template>
    </Dialog>
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource, TimePicker, Dialog, FormControl } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../../../event-bus'

const show = defineModel('show')
const event = defineModel('event')
const isInvalidForm = ref(false)


const editFormSchema = yup.object({
  eventName: yup.string().required().label("Event Name"),
  eventVenue: yup.string(),
  eventColor: yup.string().required().label("Color"),
  eventPerson: yup.string(),


  eventStartDate: yup
    .date()
    .nullable()
    .typeError("Start Date is required")
    .required("Start Date is required"),

  eventEndDate: yup
    .date()
    .nullable()
    .typeError("End Date is required")
    .required("End Date is required")
    .min(yup.ref("eventStartDate"), "End Date cannot be before Start Date"),

  eventStartTime: yup.string().required().label("Start Time"),
  eventEndTime: yup
    .string()
    .required()
    .test(
      "end-after-start",
      "End time cannot be before start time",
      function (endTime) {
        const {
          eventStartDate,
          eventEndDate,
          eventStartTime,
        } = this.parent

        if (
          !eventStartDate ||
          !eventEndDate ||
          !eventStartTime ||
          !endTime
        ) {
          return true
        }

        const startDate = new Date(eventStartDate)
        const endDate = new Date(eventEndDate)

        const [sh, sm] = eventStartTime.split(":").map(Number)
        const [eh, em] = endTime.split(":").map(Number)

        const start = new Date(startDate)
        start.setHours(sh, sm, 0, 0)

        const end = new Date(endDate)
        end.setHours(eh, em, 0, 0)

        return end.getTime() >= start.getTime()
      }
    )
    .label("End Time"),
})

const { values, meta, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});

const [eventName, eventNameAttrs] = defineField('eventName')
const [eventPerson, eventPersonAttrs] = defineField('eventPerson')
const [eventStartDate, eventStartDateAttrs] = defineField('eventStartDate')
const [eventEndDate, eventEndDateAttrs] = defineField('eventEndDate')
const [eventStartTime, eventStartTimeAttrs] = defineField('eventStartTime')
const [eventEndTime, eventEndTimeAttrs] = defineField('eventEndTime')
const [eventVenue, eventVenueAttrs] = defineField('eventVenue')
const [eventColor, eventColorAttrs] = defineField('eventColor')


let updateEvent = null

watch(event, (val) => {
  if (!val?.calendarEvent) return

  setValues({
    eventName: val.calendarEvent.title,
    eventStartDate: val.calendarEvent.fromDate,
    eventEndDate: val.calendarEvent.toDate,
    eventStartTime: val.calendarEvent.fromTime,
    eventEndTime: val.calendarEvent.toTime,
    eventVenue: val.calendarEvent.venue,
    eventColor: val.calendarEvent.color,
    eventFullDay: val.calendarEvent.isFullDay,
  })


  if (!updateEvent) {
    updateEvent = createDocumentResource({
      doctype: 'Action',
      name: val.calendarEvent.title, 
    })
  }
}, { immediate: true })


async function editOnSucess(values, { resetForm }) {
  if (!updateEvent) return

  await updateEvent.setValue.submit({
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


watch(
  () => values.eventStartDate,
  (newVal) => {
    if (!newVal) return
    setValues({
      eventEndDate: newVal,
    })
  }
)

</script>