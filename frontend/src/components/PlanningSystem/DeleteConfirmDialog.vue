<template>
    <div>
        <Dialog 
        :options="{
            title: 'Confirm Delete',
            description: 'Confirm Delete',                
        
        }"
        v-model="show"
        
        >
        <template #body-content>
        <div class="flex-col space-y-4 justify-center">
            <h3 class="mb-6 flex justify-center">Are you sure you want to Delete the selected Nodes?</h3>
            <div class="flex justify-center space-x-6">
                <Button
                    variant="outline"
                    size="xl"
                    @click="show = false"
                >
                    Cancel
                </Button>
                <Button
                    variant="solid"
                    size="xl"
                    theme="red"
                    @click="onDelete()"
                >
                    Delete
                </Button>              
            </div>
        </div>
    </template>



    </Dialog>        
    </div>
</template>
<script setup>
import { Dialog, Button } from 'frappe-ui'
import { emitter } from '../../event-bus'

const show = defineModel('show')

function onDelete(){
    emitter.emit('goal-delete-selected')
}



</script>
