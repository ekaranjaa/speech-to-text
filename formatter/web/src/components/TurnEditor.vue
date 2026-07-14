<script setup lang="ts">
import { watch } from "vue"
import { EditorContent, useEditor } from "@tiptap/vue-3"
import StarterKit from "@tiptap/starter-kit"
import { htmlToMd, mdToHtml } from "@/lib/md"
import type { Turn } from "@/lib/types"

const props = defineProps<{ turn: Turn }>()
const emit = defineEmits<{ (e: "update", value: Turn): void }>()

const editor = useEditor({
  extensions: [StarterKit],
  content: mdToHtml(props.turn.text),
  onUpdate: ({ editor }) => {
    emit("update", { ...props.turn, text: htmlToMd(editor.getHTML()) })
  },
})

// Re-hydrate when a formatted turn streams in and replaces the text.
watch(
  () => props.turn.text,
  (text) => {
    if (editor.value && htmlToMd(editor.value.getHTML()) !== text) {
      editor.value.commands.setContent(mdToHtml(text), false)
    }
  },
)

function onSpeaker(e: Event) {
  emit("update", { ...props.turn, speaker: (e.target as HTMLInputElement).value })
}
function toggleItalic() {
  editor.value?.chain().focus().toggleItalic().run()
}
</script>
<template>
  <div class="rounded-lg border border-neutral-200 p-3">
    <div class="mb-2 flex items-center gap-2">
      <input
        :value="turn.speaker"
        @input="onSpeaker"
        class="w-48 rounded border border-neutral-300 px-2 py-1 text-sm font-semibold"
      />
      <button class="rounded px-2 py-1 text-sm italic hover:bg-neutral-100" @click="toggleItalic">
        i
      </button>
    </div>
    <editor-content :editor="editor" class="prose prose-sm max-w-none focus:outline-none" />
  </div>
</template>
