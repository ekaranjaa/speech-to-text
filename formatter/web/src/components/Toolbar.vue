<script setup lang="ts">
import type { Profile } from "@/lib/types"
import Button from "@/components/ui/Button.vue"

defineProps<{ profiles: Profile[]; profileId: string; busy: boolean; canExport: boolean }>()
const emit = defineEmits<{
  (e: "upload", file: File): void
  (e: "update:profileId", value: string): void
  (e: "format"): void
  (e: "export", format: string): void
}>()

function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) emit("upload", file)
}
</script>
<template>
  <div class="flex flex-wrap items-center gap-3">
    <label class="cursor-pointer">
      <input type="file" accept="audio/*,video/*" class="hidden" @change="onFile" />
      <span
        class="inline-flex rounded-md border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100"
        >Upload audio</span
      >
    </label>
    <select
      :value="profileId"
      @change="emit('update:profileId', ($event.target as HTMLSelectElement).value)"
      class="rounded-md border border-neutral-300 px-3 py-2 text-sm"
    >
      <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
    </select>
    <Button :disabled="busy || !canExport" @click="emit('format')">Format</Button>
    <span class="mx-1 h-6 w-px bg-neutral-200" />
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'srt')">SRT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'vtt')">VTT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'txt')">TXT</Button>
    <Button variant="outline" :disabled="!canExport" @click="emit('export', 'md')">MD</Button>
  </div>
</template>
