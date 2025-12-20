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
            type="date"
            size="sm"
            variant="subtle"
            placeholder="date"
            label="Start Date"
            v-model="eventStartDate"
            v-bind="eventStartDateAttrs"
            />
            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="End Date"
            v-model="eventEndDate"
            v-bind="eventEndDateAttrs"
            />
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
            
        </div>
    </template>
    </Dialog>
    </div>
</template>
<script setup>
import {ref, watch} from 'vue'
import { ErrorMessage, createDocumentResource } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    
import {emitter} from '../event-bus'

const show = defineModel('show')
const event = defineModel('event')



const editFormSchema = yup.object({
  eventName: yup.string().required().label("Event Name"),
  eventVenue: yup.string(),
  eventColor: yup.string().required().label("Color"),
  eventPerson: yup.string(),
})

const { values, errors, defineField, handleSubmit, setValues } = useForm({
  validationSchema: editFormSchema
});

const [eventName, eventNameAttrs] = defineField('eventName')
const [eventPerson, eventPersonAttrs] = defineField('eventPerson')
const [eventStartDate, eventStartDateAttrs] = defineField('eventStartDate')
const [eventEndDate, eventEndDateAttrs] = defineField('eventEndDate')
const [eventVenue, eventVenueAttrs] = defineField('eventVenue')
const [eventColor, eventColorAttrs] = defineField('eventColor')


let updateEvent = null

watch(event, (val) => {
  if (!val?.calendarEvent) return

  setValues({
    eventName: val.calendarEvent.title,
    eventStartDate: val.calendarEvent.fromDate,
    eventEndDate: val.calendarEvent.toDate,
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
    start_date: values.eventStartDate,
    end_date: values.eventEndDate,
    color: values.eventColor,
    full_day: values.eventFullDay,
  })

  resetForm()
  show.value = false
  emitter.emit('event-update')
}

const onSubmit = handleSubmit(editOnSucess)


</script>