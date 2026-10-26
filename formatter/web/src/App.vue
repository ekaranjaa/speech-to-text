<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { api } from "@/lib/api"
import { groupTurns } from "@/lib/turns"
import type { Profile, Turn } from "@/lib/types"
import Toolbar from "@/components/Toolbar.vue"
import TurnEditor from "@/components/TurnEditor.vue"

const profiles = ref<Profile[]>([])
const profileId = ref("")
const turns = ref<Turn[]>([])
const busy = ref(false)
const status = ref("")

const canExport = computed(() => turns.value.length > 0)

onMounted(async () => {
  try {
    profiles.value = await api.listProfiles()
    if (profiles.value.length) profileId.value = profiles.value[0].id
  } catch (e) {
    status.value = `Could not load profiles: ${(e as Error).message}`
  }
})

async function onUpload(file: File) {
  busy.value = true
  status.value = "Diarizing… (first run downloads models on the host)"
  try {
    const result = await api.diarize(file)
    turns.value = groupTurns(result.segments)
    status.value = `${result.speakers.length} speaker(s), ${turns.value.length} turns.`
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  } finally {
    busy.value = false
  }
}

async function onFormat() {
  busy.value = true
  status.value = "Formatting…"
  try {
    const segments = turns.value.map((t) => ({ ...t }))
    const formatted: Turn[] = []
    for await (const turn of api.formatSegments(segments, profileId.value)) {
      formatted.push(turn)
      turns.value = [...formatted]
    }
    status.value = "Done."
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  } finally {
    busy.value = false
  }
}

async function onExport(format: string) {
  try {
    const { blob, filename } = await api.exportSegments(
      turns.value.map((t) => ({ ...t })),
      format,
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    status.value = `Error: ${(e as Error).message}`
  }
}

function updateTurn(i: number, value: Turn) {
  turns.value[i] = value
}
</script>
<template>
  <main class="mx-auto max-w-4xl space-y-5 p-6">
    <header>
      <h1 class="text-2xl font-semibold">Transcript Studio</h1>
      <p class="text-sm text-neutral-500">
        Upload audio → diarize → edit speakers &amp; text → format → export.
        <a href="/manage" class="underline">Manage profiles</a>
      </p>
    </header>

    <Toolbar
      :profiles="profiles"
      v-model:profileId="profileId"
      :busy="busy"
      :can-export="canExport"
      @upload="onUpload"
      @format="onFormat"
      @export="onExport"
    />

    <p v-if="status" class="text-sm text-neutral-600">{{ status }}</p>

    <section class="space-y-3">
      <TurnEditor v-for="(turn, i) in turns" :key="i" :turn="turn" @update="(v) => updateTurn(i, v)" />
      <p v-if="!turns.length" class="text-sm text-neutral-400">
        No transcript yet. Upload an audio file to begin.
      </p>
    </section>
  </main>
</template>
