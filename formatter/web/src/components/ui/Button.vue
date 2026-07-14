<script setup lang="ts">
import { cn } from "@/lib/cn"
defineProps<{ variant?: "default" | "outline" | "ghost" }>()
const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:pointer-events-none"
const variants = {
  default: "bg-neutral-900 text-white hover:bg-neutral-800",
  outline: "border border-neutral-300 hover:bg-neutral-100",
  ghost: "hover:bg-neutral-100",
}
</script>
<template>
  <button :class="cn(base, variants[variant ?? 'default'])"><slot /></button>
</template>
