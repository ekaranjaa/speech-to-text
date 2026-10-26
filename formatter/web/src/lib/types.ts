export interface Segment {
  start: number
  end: number
  speaker: string
  text: string
}

export type Turn = Segment

export interface Profile {
  id: string
  name: string
  description: string
}

export interface DiarizeResult {
  segments: Segment[]
  speakers: string[]
  language: string
}
