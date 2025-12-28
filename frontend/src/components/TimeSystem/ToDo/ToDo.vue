<template>
  <div class="h-screen flex flex-col justify-center items-center">
    <div class="w-full p-10 !pt-5 flex justify-center border-b-2 relative">
      <div class="w-1/6 h-full flex justify-center items-center text-xl">
        {{ formattedDate }}
      </div>

      <!-- Middle: todo input -->
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
            <Popover trigger="hover">
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
                  Reminder, R: Enable and Set Duration before End Date Time at which Reminder will trigger (1d 1h 15m or 2025/02/01)
                </div>
              </template>
            </Popover>
          </template>
        </FormControl>
        <ErrorMessage class="mt-2" :message="errorMessage" />
      </div>


      <div class="w-1/6 h-full relative flex flex-col items-start">
        <div class="absolute -top-5 left-0 text-sm font-medium text-gray-600">
          Date Range Filter
        </div>

        <DateRangePicker
          v-model="dateRangeValue"
          variant="subtle"
          placeholder="Date Filter"
          class="w-full"
        />
      </div>

    </div>
    
    <div class="w-full h-full !p-0 overflow-y-auto">
      <div class="flex flex-col min-h-full" ref="listContainer">
        <div v-if="!loading">
        <Sortable :data="pending" class="!pb-0 !min-h-0"  :groups="['pending']">
          <TransitionGroup name="task-list" tag="div" class="task-transition-group">
            <div
              v-for="(task, index) in pending"
              :key="task.name"
              :index="index"
              class="!py-1 "
            >
              <SortableItem
                :groups="['pending']"
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


        <Sortable v-show="!collapsed" :data="completed" class="!p-0 !min-h-0" :groups="['tasks']">
          <TransitionGroup name="task-list" tag="div" class="task-transition-group">
            <div
              v-for="(task, index) in completed"
              :key="task.name"
              :index="index"
              class="!pt-1"
            >
              <SortableItem
                :groups="['completed']"
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

        <div class="flex-1 !px-5 overflow-hidden">
          <div
            v-for="(i, idx) in fillerCount"
            :key="i"
            class="h-15 w-full border-b-2 border-black"
            :class="idx === 0 && 'border-t-2'"
          />
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
  </div>
</template>
<script setup>
import { ListView, createListResource, FormControl, LoadingText, ErrorMessage, Popover, DateRangePicker } from 'frappe-ui';
import { reactive, ref, watch, computed, onMounted, nextTick, watchEffect }  from 'vue'

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

const listContainer = ref(null)
const ROW_HEIGHT = 62

const fillerCount = ref(0)

function recalcFillers() {
  if (!listContainer.value) return

  const containerHeight = listContainer.value.clientHeight
  const taskCount =
    pending.value.length +
    1 + 
    (collapsed.value ? 0 : completed.value.length)

  const usedHeight = taskCount * ROW_HEIGHT

  if (usedHeight >= containerHeight) {
    fillerCount.value = 0
    return
  }

  const remaining = containerHeight - usedHeight
  fillerCount.value = Math.floor(remaining / ROW_HEIGHT)
}

watchEffect(async () => {
  await nextTick()  
  recalcFillers()
})

watch(
  [pending, completed, collapsed],
  () => nextTick(recalcFillers),
  { deep: true }
)



function handleClick(actionName) {
  showEdit.value = true

  const match = todos.data.find(
    todo => todo.action_name === actionName
  )

  sendTodo.value = match ? { ...match } : null
}

const today = new Date()

const startInit = new Date(today)
startInit.setDate(today.getDate() - 7)

const endInit = new Date(today)
endInit.setDate(today.getDate() + 7)

const _dateRange = ref([startInit, endInit])

const dateRangeValue = computed({
  get() {
    return _dateRange.value
  },
  set([start, end]) {
    if (start && end && start > end) {
      // auto-fix: swap or clamp
      _dateRange.value = [end, start]
    } else {
      _dateRange.value = [start, end]
    }
  }
})


let todos = createListResource({
  doctype: 'Action',
  fields: ['action_name', 'reminder', 'completed', 'name', 'color',  'starred', 'start_date', 'end_date', 'starred', 'estimated_hours'],
    filters: {
        todo: 1
    },  
  orderBy: 'creation desc',
})
todos.fetch()

watch(
  () => _dateRange.value,
  ([start, end]) => {
    // no range → reset
    if (!start || !end) {
      todos.filters = { todo: 1 }
      todos.fetch()
      return
    }

    // overlap condition:
    // action.start_date <= rangeEnd
    // AND action.end_date >= rangeStart
    todos.filters = {
      todo: 1,
      start_date: ['<=', end],
      end_date: ['>=', start],
    }

    todos.fetch()
  },
  { deep: true }
)
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

function getDateRange(byValue, atValue, durationValue, fromValue) {
  const today = new Date();

  const pad = n => String(n).padStart(2, "0");
  const fmt = d =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

  // ---------- TIME ----------
  function parseTime(str) {
    if (!str) return null;

    const s = str.trim().toLowerCase().replace(/\s+/g, "");
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

  // ---------- VALID DATE TOKENS ----------
  const validDateTokens = new Set([
    "today",
    "tomorrow",
    ...Object.keys(days),
  ]);

  function isValidDateToken(token) {
    if (!token) return true;
    return validDateTokens.has(token.trim().toLowerCase());
  }

  // ---------- APPLY DATE (FROM) ----------
  function applyFromDate(date, token) {
    if (!token) return;

    const t = token.trim().toLowerCase();

    if (!isValidDateToken(t)) {
      errorMessage.value = "Invalid By or From Format. Check your spelling";
      throw new Error("Invalid FROM");
    }

    if (t === "today") {
      date.setFullYear(today.getFullYear(), today.getMonth(), today.getDate());
      return;
    }

    if (t === "tomorrow") {
      date.setDate(date.getDate() + 1);
      return;
    }

    if (days[t] !== undefined) {
      let diff = days[t] - date.getDay();
      if (diff < 0) diff += 7;
      date.setDate(date.getDate() + diff);
    }
  }

  // ---------- APPLY DATE (BY) ----------
  function applyByDate(date, token, fromDate) {
    if (!token) return;

    const t = token.trim().toLowerCase();

    if (!isValidDateToken(t)) {
      errorMessage.value = "Invalid By or From Format. Check your spelling";
      throw new Error("Invalid BY");
    }

    if (t === "today") {
      date.setFullYear(today.getFullYear(), today.getMonth(), today.getDate());
      return;
    }

    if (t === "tomorrow") {
      date.setDate(date.getDate() + 1);
      return;
    }

    if (days[t] !== undefined) {
      const target = days[t];
      const fromDay = fromDate.getDay();
      let diff = target - date.getDay();

      if (target >= fromDay) {
        if (diff < 0) diff += 7;
      } else {
        if (diff > 0) diff -= 7;
      }

      date.setDate(date.getDate() + diff);
    }
  }

  // ---------- INIT ----------
  let start = new Date(today);
  let end = new Date(today);

  // ---------- FROM ----------
  if (fromValue) {
    try {
      const parts = fromValue.trim().split(/\s+/);
      applyFromDate(start, parts[0]);

      const time = parseTime(parts.slice(1).join(""));
      if (time) start.setHours(time.h, time.min, 0, 0);
    } catch {
      return null;
    }
  }

  // ---------- AT ----------
  if (atValue) {
    const normalized = atValue.replace(/\s*-\s*/g, " to ");
    const parts = normalized.split(/\s+to\s+/i);

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
  }

  // ---------- BY ----------
  if (byValue) {
    try {
      const byDate = new Date(end);
      applyByDate(byDate, byValue, start);

      if (byDate > end) end = byDate;
      if (byDate < end) end = byDate;
    } catch {
      return null;
    }
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
  if (!result.By && !result.At) {
    errorMessage.value = "Format is not correct. Missing date or time.";
    return;
  }

  function isInvalidDateFormat(value) {
    if (!value) return false;
    const looksLikeDate = /\d/.test(value) && value.includes("/");
    if (!looksLikeDate) return false;

    const strict = /^(\d{4})\/(\d{2})\/(\d{2})$/;
    const m = value.match(strict);
    if (!m) return true;

    const y = +m[1], mo = +m[2], d = +m[3];
    if (mo < 1 || mo > 12) return true;
    if (d < 1 || d > 31) return true;

    return false;
  }

  if (isInvalidDateFormat(result.By)) {
    errorMessage.value = "Invalid date format for 'By'. Use YYYY/MM/DD.";
    return;
  }

  if (isInvalidDateFormat(result.From)) {
    errorMessage.value = "Invalid date format for 'From'. Use YYYY/MM/DD.";
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

  if (parent === "") parent = "Administrator-ACT-000001";

  const dateRange = getDateRange(result.By, result.At, hours, result.From);

  if (!dateRange) return;

  // ---------- REMINDER LOGIC (FINAL) ----------
  function formatDateTime(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    const h = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    const s = String(date.getSeconds()).padStart(2, "0");
    return `${y}/${m}/${d} ${h}:${mi}:${s}`;
  }

  function computeReminder(reminderInput, endDate) {
    if (!reminderInput) return null;

    const end = endDate instanceof Date ? endDate : new Date(endDate);
    if (isNaN(end)) return null;

    // 1️⃣ explicit datetime: YYYY/MM/DD HH:mm or HH:mm:ss
    const dateTimeRegex =
      /^(\d{4})\/(\d{2})\/(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/;

    let m = reminderInput.match(dateTimeRegex);
    if (m) {
      const [, y, mo, d, h, mi, s] = m.map(Number);
      return formatDateTime(
        new Date(y, mo - 1, d, h, mi, s || 0)
      );
    }

    // 2️⃣ explicit date only: YYYY/MM/DD → midnight
    const dateOnlyRegex = /^(\d{4})\/(\d{2})\/(\d{2})$/;
    if (dateOnlyRegex.test(reminderInput)) {
      const [y, mo, d] = reminderInput.split("/").map(Number);
      return formatDateTime(new Date(y, mo - 1, d, 0, 0, 0));
    }

    // 3️⃣ duration: 1d 2h 15m
    let totalMs = 0;
    const durRegex = /(\d+)\s*(d|h|m)/gi;
    let match;

    while ((match = durRegex.exec(reminderInput)) !== null) {
      const v = Number(match[1]);
      if (match[2].toLowerCase() === "d") totalMs += v * 86400000;
      if (match[2].toLowerCase() === "h") totalMs += v * 3600000;
      if (match[2].toLowerCase() === "m") totalMs += v * 60000;
    }

    if (!totalMs) return null;

    return formatDateTime(new Date(end.getTime() - totalMs));
  }

  const reminder = computeReminder(result.Reminder, dateRange.end);

  if (errorMessage.value === "") {
    todos.insert.submit({
      action_name: result.todo,
      parent_action: parent,
      start_date: dateRange.start,
      end_date: dateRange.end,
      reminder: reminder,
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