<template>
    <div>
    <Dialog 
    :options="{
        title: 'New Event',
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
            />
            <ErrorMessage :message="errors.eventName" />

            <FormControl 
            type="text"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Person"
            v-model="eventPerson"
            v-bind="eventPersonAttrs"
            />
            <ErrorMessage :message="errors.eventPerson" />
            
            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="date"
            label="Start Date"
            v-model="eventStartDate"
            v-bind="eventStartDateAttrs"
            @change="val => eventStartDate = val?.toISOString?.().slice(0,10) ?? val"
            />
            <FormControl 
            type="date"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="End Date"
            v-model="eventEndDate"
            v-bind="eventEndDateAttrs"
            @change="val => eventStartDate = val?.toISOString?.().slice(0,10) ?? val"
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
                label: 'Red',
                value: 'Red',
            },
            {
                label: 'Green',
                value: 'Green',
            },
            {
                label: 'Yellow',
                value: 'Yellow',
            },
            ]"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Color"
            v-model="eventColor"
            v-bind="eventColorAttrs"
            />
            <ErrorMessage :message="errors.eventColor" />
            <FormControl 
            type="checkbox"
            size="sm"
            variant="subtle"
            placeholder="John Doe"
            label="Full Day Event?"
            v-model="eventFullDay"
            v-bind="eventFullDayAttrs"
            />
        </div>
    </template>
    </Dialog>

    </div>
</template>
<script setup>
import {ref} from 'vue'
import { ErrorMessage } from 'frappe-ui'
import * as yup from 'yup'
import {useForm} from 'vee-validate'    


const editFormSchema = yup.object({
  eventName: yup.string().required().label("Event Name"),
  eventVenue: yup.string(),
  eventColor: yup.string().required().label("Color"),
  eventPerson: yup.string(),
})

const { values, errors, defineField, handleSubmit } = useForm({
  validationSchema: editFormSchema
});



const [eventName, eventNameAttrs] = defineField('eventName')
const [eventPerson, eventPersonAttrs] = defineField('eventPerson')
const [eventStartDate, eventStartDateAttrs] = defineField('eventStartDate')
const [eventEndDate, eventEndDateAttrs] = defineField('eventEndDate')
const [eventVenue, eventVenueAttrs] = defineField('eventVenue')
const [eventColor, eventColorAttrs] = defineField('eventColor')
const [eventFullDay, eventFullDayAttrs] = defineField('eventFullDay')

function editOnSucess(values, {resetForm}){
  console.log(values)
  resetForm()
  show.value = false
}

const onSubmit = handleSubmit(editOnSucess, )


const show = defineModel('show')
const data = defineModel('data')

</script>