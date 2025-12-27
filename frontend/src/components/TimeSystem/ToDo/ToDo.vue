<template>
  <div class="h-screen flex flex-col justify-center items-center">
    <div class="w-full p-10 flex justify-center border-b-2 ">
      <div class="w-1/6 h-full flex justify-center items-center text-xl">{{ formattedDate }}</div>
      <div class="w-4/6 h-full mx-4 min-w-60">
      <FormControl
        v-model="toDoValue"
        class="w-full"
        type="text"
        variant="outline"
        :placeholder="formDisplay.placeholder"
        @focus="onFocus"
        @blur="onBlur"
        @keydown.enter="createTodo(toDoValue)"
        size="xl"
      >
        <template #prefix>
          <Component :is="formDisplay.icon" :size="20" />
        </template>
        <template #suffix>
          <Popover
            trigger="hover"
          >
            <template #target>
              <Info :size="24"/>
            </template>
            <template #body-main>
              <div class="p-2 text-ink-gray-9">
                Under, U: Set Parent Action <br/>
                From, F: Set the Start Date (tomorrow, Wednesday, 2025/02/01) <br/>
                By, B: Set End Date (tomorrow, Wednesday, 2025/02/01) <br/>
                At, A: Set Start Date Time and End Date Time (08:23 to 9pm) <br/>
                Duration, D: Set Todo Estimated Duration (4h) <br/>
                Important, I: Set Starred <br/>
                Reminder, R: Enable and Set Duration before End Date Time at which Reminder will trigger (15m)
              </div>
            </template>
          </Popover>
        </template>
      </FormControl>
      <ErrorMessage class="mt-2" :message="errorMessage" />
      </div>
      <div class="w-1/6"></div>
    </div>
    
    <div class="w-full h-full !p-0 overflow-y-auto ">
      <div v-if="!loading">
      <Sortable :data="pending" class="!pb-0 !min-h-0" >
        <TransitionGroup name="task-list" tag="div" class="task-transition-group">
          <div
            v-for="(task, index) in pending"
            :key="task.name"
            :index="index"
            class="!py-1 "
          >
            <SortableItem
              @dblclick="() => handleClick(task.action_name)"
              :source="pending"
              :index="index"
              class="!p-0 !m-0 w-full h-15 flex !rounded-lg border-b-2 border-white"
            >
              <ToDoContainer :todos="task.action_name" :completed="false" :control="todos" :id="task.name" :starred="task.starred"/>
            </SortableItem>
          </div>
        </TransitionGroup>
      </Sortable>



    <div class="!px-[1rem] !pb-1">
      <div
        class="cursor-pointer h-15 max-w-40 flex items-center px-2
              overflow-hidden
              !rounded-lg !shadow-[0_1px_2px_rgba(0,0,0,0.2)] !bg-[#D3D3D3]"
        @click="collapsed = !collapsed"
      >
        <span class="whitespace-nowrap overflow-hidden text-clip">
          Completed
        </span>
        <span class="ml-auto w-4 text-center flex-shrink-0">
          {{ collapsed ? '▸' : '▾' }}
        </span>
      </div>


      <Sortable v-show="!collapsed" :data="completed" class="!p-0 !min-h-0">
        <TransitionGroup name="task-list" tag="div" class="task-transition-group">
          <div
            v-for="(task, index) in completed"
            :key="task.name"
            :index="index"
            class="!pt-1"
          >
            <SortableItem
              @dblclick="() => handleClick(task.action_name)"
              :source="completed" 
              :index="index"
              class="!p-0 !m-0 w-full h-15 flex !rounded-lg border-b-2 border-white"
            >
              <ToDoContainer :todos="task.action_name" :completed="true" :control="todos" :id="task.name" :starred="task.starred"/>
            </SortableItem>
          </div>
        </TransitionGroup>
      </Sortable>
    </div>

      <div class="!px-5">
        <div class="h-15 w-100  border-y-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
        <div class="h-15 w-100  border-b-2 border-black" ></div>
      </div>
      </div>
      <LoadingText
      v-if="loading"
      text="Loading Todos..."
      class="absolute inset-0 flex items-center justify-center text-5xl scale-150"
      />    
    </div>
    <CreateToDoForm v-model:show="showEdit" :data="sendTodo" :key="sendTodo.name"/>
  </div>
</template>
<script setup>
import { ListView, createListResource, FormControl, LoadingText, ErrorMessage, Popover } from 'frappe-ui';
import { reactive, ref, watch, computed, onMounted }  from 'vue'

import { Plus, Circle, CircleCheck, Star, Info } from 'lucide-vue-next';
import ToDoContainer from './ToDoContainer.vue';
import CreateToDoForm from './EditToDoForm.vue';
import { useDraggable, useDroppable } from '@vue-dnd-kit/core';
import { Sortable, SortableItem } from '../../Sortable/index';
import { emitter } from '../../../event-bus';

const toDoValue = ref("")
const showEdit = ref(false)
const errorMessage = ref('')
const loading = ref(true)
const collapsed = ref(true)
const pending = ref([]);
const completed = ref([])

const sendTodo = ref({})

function handleClick(actionName) {
  showEdit.value = true

  const match = todos.data.find(
    todo => todo.action_name === actionName
  )

  sendTodo.value = match ? { ...match } : null
}

let todos = createListResource({
  doctype: 'Action',
  fields: ['action_name', 'completed', 'name', 'color',  'starred', 'start_date', 'end_date', 'starred', 'estimated_hours'],
    filters: {
        todo: 1
    },  
  orderBy: 'creation desc',
})
todos.fetch()
watch(
  () => todos.data,
  (newTodos) => {
    if (!newTodos) return
    
    pending.value = []
    completed.value = []

    for (const todo of newTodos) {
      if (todo.completed === 0 || todo.completed === "0") {
        pending.value.push(todo)
      } else {
        completed.value.push(todo)
      }
    }
    loading.value = false
  },
  { immediate: true }
)

emitter.on("todos_updated", async ()=>{
  await todos.reload()
})



const formDisplay = reactive({
  icon: Plus,
  placeholder: "Add a ToDo"
})

function onFocus(){
  formDisplay.icon = Circle
  if (toDoValue.value === "") {
    formDisplay.placeholder = "Todo By Wednesday At 04:30 to 6pm"
  }
}

function onBlur(){
    if (toDoValue.value === "") {
    formDisplay.placeholder = "Add a ToDo"  
    formDisplay.icon = Plus
  }
}

const formattedDate = computed(() =>
  new Date().toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long'
  })
)

function getDateRangeFromBy(byValue, atValue, durationValue, fromValue) {
  const today = new Date();

  const pad = n => String(n).padStart(2, "0");
  const fmt = d =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

  // ---------- TIME ----------
  function parseTime(str) {
    if (!str) return null;
    const s = str.trim().toLowerCase();
    const m = s.match(/^(\d{1,2})(?::(\d{2}))?(am|pm)?$/);
    if (!m) return null;

    let h = Number(m[1]);
    const min = Number(m[2] || 0);
    const ap = m[3];

    if (ap === "pm" && h !== 12) h += 12;
    if (ap === "am" && h === 12) h = 0;

    return { h, min };
  }

  const days = {
    sunday: 0, monday: 1, tuesday: 2, wednesday: 3,
    thursday: 4, friday: 5, saturday: 6,
  };

  // ---------- APPLY DATE (FROM) ----------
  function applyFromDate(date, token) {
    if (!token) return;
    const t = token.trim().toLowerCase();

    if (t === "today") {
      date.setFullYear(today.getFullYear(), today.getMonth(), today.getDate());
      return;
    }

    if (days[t] !== undefined) {
      let diff = days[t] - date.getDay();
      if (diff < 0) diff += 7;
      date.setDate(date.getDate() + diff);
    }
  }

  // ---------- APPLY DATE (BY — SMART) ----------
  function applyByDate(date, token, fromDate) {
    if (!token) return;
    const t = token.trim().toLowerCase();

    if (t === "today") {
      date.setFullYear(today.getFullYear(), today.getMonth(), today.getDate());
      return;
    }

    if (days[t] !== undefined) {
      const target = days[t];
      const fromDay = fromDate.getDay();

      let diff = target - date.getDay();

      // 🔑 decide direction
      if (target >= fromDay) {
        if (diff < 0) diff += 7;   // forward
      } else {
        if (diff > 0) diff -= 7;   // backward
      }

      date.setDate(date.getDate() + diff);
    }
  }

  // ---------- INIT ----------
  let start = new Date(today);
  let end = new Date(today);

  // ---------- FROM ----------
  if (fromValue) {
    const parts = fromValue.trim().split(/\s+/);
    applyFromDate(start, parts[0]);

    const time = parseTime(parts.slice(1).join(""));
    if (time) start.setHours(time.h, time.min, 0, 0);
  }

  // ---------- AT ----------
  if (atValue) {
    const parts = atValue.split(/\s+to\s+/i);

    if (parts.length === 2) {
      const s = parseTime(parts[0]);
      const e = parseTime(parts[1]);
      if (!s || !e) return null;

      start.setHours(s.h, s.min, 0, 0);
      end = new Date(start);
      end.setHours(e.h, e.min, 0, 0);
    } else {
      const t = parseTime(parts[0]);
      if (!t) return null;

      if (!fromValue) start.setHours(t.h, t.min, 0, 0);
      end = new Date(start);

      if (durationValue > 0) {
        end = new Date(start.getTime() + durationValue * 60 * 60000);
      }
    }
  } else {
    end = new Date(start);
    if (durationValue > 0) {
      end = new Date(start.getTime() + durationValue * 60 * 60000);
    }
  }

  // ---------- BY ----------
  if (byValue) {
    const byDate = new Date(end);
    applyByDate(byDate, byValue, start);

    if (byDate > end) end = byDate;
    if (byDate < end) end = byDate;
  }

  // ---------- VALIDATION ----------
  if (end < start) {
    errorMessage.value = "Start Time Cannot be Before End Time";
    return null;
  }

  return {
    start: fmt(start),
    end: fmt(end),
  };
}





function createTodo(input) {
  errorMessage.value = "";

  const keywords = [
    "Under",
    "By",
    "From",      
    "At",
    "Duration",
    "Reminder",
    "Important"
  ];

  const aliasMap = Object.fromEntries(
    keywords.map(k => [k[0].toUpperCase(), k])
  );

  const allKeys = [...keywords, ...Object.keys(aliasMap)];

  const firstKeywordRegex = new RegExp(`\\b(${allKeys.join("|")})\\b`, "i");
  const firstMatch = input.match(firstKeywordRegex);

  const result = {};
  result.todo = firstMatch
    ? input.slice(0, firstMatch.index).trim()
    : input.trim();

  const pattern = new RegExp(
    `\\b(${allKeys.join("|")})\\b([\\s\\S]*?)(?=\\b(${allKeys.join("|")})\\b|$)`,
    "gi"
  );

  let match;
  while ((match = pattern.exec(input)) !== null) {
    const rawKey = match[1];
    const value = match[2].trim();

    const normalizedKey =
      keywords.find(k => k.toLowerCase() === rawKey.toLowerCase()) || rawKey;

    const fullKey = aliasMap[rawKey] || normalizedKey;

    if (fullKey === "Important") {
      result.important = 1;
      continue;
    }

    result[fullKey] = value;
    result[fullKey[0]] = value;
  }

  if (result.important === undefined) result.important = 0;

  // ---- VALIDATION ----
  const hasBy = !!result.By;
  const hasAt = !!result.At;

  if (!hasBy && !hasAt) {
    errorMessage.value = "Format is not correct. Missing date or time.";
    return;
  }

  // ---- DATE FORMAT VALIDATION ----
  function isInvalidDateFormat(value) {
    if (!value) return false;

    // If it contains digits and slashes, treat it as a date attempt
    const looksLikeDate = /\d/.test(value) && value.includes("/");

    if (!looksLikeDate) return false;

    // Enforce strict YYYY/MM/DD
    const strictDateRegex = /^(\d{4})\/(\d{2})\/(\d{2})$/;
    const match = value.match(strictDateRegex);

    if (!match) return true; // wrong format

    const year = parseInt(match[1], 10);
    const month = parseInt(match[2], 10);
    const day = parseInt(match[3], 10);

    // Check valid month/day ranges
    if (month < 1 || month > 12) return true;
    if (day < 1 || day > 31) return true;

    return false; // valid date format
  }

  if (isInvalidDateFormat(result.By)) {
    errorMessage.value = "Invalid date format for 'By'. Use YYYY/MM/DD with valid month/day.";
    return;
  }

  if (isInvalidDateFormat(result.From)) {
    errorMessage.value = "Invalid date format for 'From'. Use YYYY/MM/DD with valid month/day.";
    return;
  }

  const hours = parseInt(result.Duration, 10);

  let parent = "";
  for (const task of todos.data) {
    if (task.action_name === result.Under) {
      parent = task.name;
      break;
    }
  }

  if (parent === "") {
    parent = "Administrator-ACT-000001";
  }

  const dateRange = getDateRangeFromBy(result.By, result.At, hours, result.From);



  if (errorMessage.value === "") {
    todos.insert.submit({
    action_name: result.todo,
    parent_action: parent,
    start_date: dateRange.start,
    end_date: dateRange.end,
    estimated_hours: hours,
    starred: result.important,
    todo: 1,
  });  
    toDoValue.value = "";
  }
}


watch(toDoValue, () => {
  errorMessage.value = "";
});



</script>
<style>
  /* TransitionGroup animations */
  .task-list-enter-active,
  .task-list-leave-active {
    transition: all 0.5s ease;
  }

  .task-list-enter-from {
    opacity: 0;
    transform: translateY(-30px);
  }

  .task-list-leave-to {
    opacity: 0;
    transform: translateY(30px);
  }

  .task-list-move {
    transition: transform 0.5s ease;
  }
</style>