<template>
    <div style="height:100%;display:flex;justify-content:center;align-items:center;color:black;">
        <div style="display:flex;flex-direction:column;">
          <span style="color: black;">
          This is a custom watermark. You can put whatever React component you want here
          </span>
          <span>
            <button @click="onAddNewPanel">Add New Panel</button>
          </span>
        </div>
    </div>
</template>
<script>
import 'dockview-vue/dist/styles/dockview.css';


export default {
    name: 'Panel',
    props: {
        params: {
            required: true,
        },
    },
    setup(props) {
        return { isGroup: props.params.containerApi.groups.length > 0 };
    },
    methods: {
        onAddNewPanel() {
            this.params.containerApi.addPanel({
                id: Date.now().toString(),
                component: 'default',
            });
        },
    },
}
</script>
