import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ALargeSmall,
  AlignLeft,
  Award,
  Bold,
  BookOpen,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileText,
  GraduationCap,
  Heading2,
  Image as ImageIcon,
  Italic,
  LayoutTemplate,
  Layers3,
  Link,
  List,
  ListOrdered,
  Plus,
  RefreshCw,
  Redo2,
  RemoveFormatting,
  Save,
  Sparkles,
  Trash2,
  Underline,
  Undo2,
  Upload,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

type JsonRecord = Record<string, unknown>

interface ResumeProfile {
  id: number
  basics: JsonRecord
  contacts: JsonRecord
  education: JsonRecord[]
  skills: string[]
  preferences: JsonRecord
  created_at?: string
  updated_at?: string
}

interface ResumeMaterial {
  id: string
  entry_id: string
  material_type: string
  content: string
  evidence: string
  tags: string[]
  jd_keywords: string[]
  strength: number
  visible: boolean
  sort_order: number
  metadata: JsonRecord
}

interface ResumeEntry {
  id: string
  section_id: string
  entry_type: string
  title: string
  organization: string
  role: string
  start_date: string
  end_date: string
  description: string
  visible: boolean
  sort_order: number
  metadata: JsonRecord
  materials: ResumeMaterial[]
}

interface ResumeSection {
  id: string
  profile_id: number
  section_type: string
  title: string
  summary: string
  visible: boolean
  sort_order: number
  metadata: JsonRecord
  entries: ResumeEntry[]
}

interface ResumeTemplate {
  id: string
  name: string
  template_type: string
  source_type: string
  layout?: JsonRecord
  style?: JsonRecord
  preview_path?: string
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

interface ResumeVersion {
  id: string
  name: string
  target_job_id?: string
  target_company: string
  target_title: string
  template_id?: string
  selected_section_ids: string[]
  selected_entry_ids: string[]
  selected_material_ids: string[]
  profile_snapshot?: ResumeSnapshot
  status: string
  updated_at?: string
}

interface ResumeSnapshot {
  profile?: ResumeProfile
  sections?: ResumeSection[]
  template?: ResumeTemplate | null
  photo?: ResumePhoto | null
  selected_section_ids?: string[]
  selected_entry_ids?: string[]
  selected_material_ids?: string[]
}

interface ResumePhoto {
  id: string
  path: string
  mime_type: string
  file_size: number
  image_url?: string
  created_at?: string
}

interface ResumePhotoCandidate {
  filename: string
  mime_type: string
  file_size: number
  image_url?: string
}

interface ResumeCenterPayload {
  profile: ResumeProfile
  photo?: ResumePhoto | null
  sections: ResumeSection[]
  templates: ResumeTemplate[]
  versions: ResumeVersion[]
}

interface ResumeImportDraft {
  source_filename: string
  photo_candidate?: ResumePhotoCandidate | null
  profile: {
    basics: JsonRecord
    contacts: JsonRecord
    education: JsonRecord[]
    skills: string[]
    preferences: JsonRecord
  }
  sections: {
    section_type: string
    title: string
    summary: string
    entries: {
      title: string
      organization: string
      role: string
      start_date: string
      end_date: string
      description: string
      materials: { content: string }[]
    }[]
  }[]
  stats: {
    education: number
    skills: number
    sections: number
    entries: number
    materials: number
  }
  warnings: string[]
  preview_excerpt: string
}

interface TemplateImportDraft {
  name: string
  source_filename: string
  base_template: string
  template_type: string
  detected: {
    sections: number
    bullets: number
    short_lines: number
    contacts: number
  }
  layout: JsonRecord
  style: JsonRecord
  preview_excerpt: string
  warnings: string[]
}

type SectionKind = {
  type: string
  title: string
  emptyText: string
  icon: typeof BriefcaseBusiness
}

const PROFILE_EMPTY: ResumeProfile = {
  id: 1,
  basics: {},
  contacts: {},
  education: [],
  skills: [],
  preferences: {},
}

const SECTION_KINDS: SectionKind[] = [
  { type: 'project', title: '项目经历', emptyText: '还没有项目经历。', icon: Layers3 },
  { type: 'work', title: '实习 / 工作经历', emptyText: '还没有实习或工作经历。', icon: BriefcaseBusiness },
  { type: 'academic', title: '学术成果', emptyText: '还没有学术成果。', icon: FileText },
  { type: 'campus', title: '校园与实践经历', emptyText: '还没有校园与实践经历。', icon: GraduationCap },
  { type: 'award', title: '荣誉奖项', emptyText: '还没有荣誉奖项。', icon: Award },
  { type: 'skill', title: '技能证书', emptyText: '还没有技能证书。', icon: BookOpen },
  { type: 'self_evaluation', title: '综合评价', emptyText: '还没有综合评价。', icon: Sparkles },
]

const tabs = [
  { id: 'profile', label: '我的资料' },
  { id: 'versions', label: '我的简历' },
  { id: 'templates', label: '模板中心' },
] as const

function valueOf(source: JsonRecord, key: string) {
  const value = source[key]
  return typeof value === 'string' ? value : ''
}

function toLines(value: string) {
  return value.split('\n').map(item => item.trim()).filter(Boolean)
}

function formatFileSize(bytes?: number) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

type PersonalCustomField = { label: string; value: string }

function customFieldsOf(source: JsonRecord): PersonalCustomField[] {
  const raw = source.custom_fields
  if (!Array.isArray(raw)) return []
  return raw
    .filter((item): item is JsonRecord => !!item && typeof item === 'object' && !Array.isArray(item))
    .map(item => ({ label: valueOf(item, 'label'), value: valueOf(item, 'value') }))
    .filter(item => item.label || item.value)
}

function templateLabel(templateId?: string) {
  if (templateId === 'compact-two-column') return '简洁双栏'
  if (templateId === 'classic-single') return '经典单栏'
  return templateId || '未选择'
}

function templateDisplayLabel(templateId: string | undefined, templates: ResumeTemplate[]) {
  const template = templates.find(item => item.id === templateId)
  return template?.name || templateLabel(templateId)
}

function templateBaseId(templateId: string, templates: ResumeTemplate[]) {
  if (templateId === 'compact-two-column' || templateId === 'classic-single') return templateId
  const template = templates.find(item => item.id === templateId)
  const base = typeof template?.layout?.base_template === 'string' ? template.layout.base_template : ''
  return base === 'compact-two-column' ? 'compact-two-column' : 'classic-single'
}

function templateAccent(template: ResumeTemplate) {
  const accent = typeof template.style?.accent === 'string' ? template.style.accent : ''
  return /^#[0-9a-f]{6}$/i.test(accent) ? accent : '#FB6511'
}

function templateTypeLabel(template: ResumeTemplate, base: string) {
  if (template.source_type === 'user') return '用户模板'
  const source = typeof template.layout?.source === 'string' ? template.layout.source : ''
  if (source) return source
  if (base === 'compact-two-column') return '双栏模板'
  return '单栏模板'
}

function templateLicenseLabel(template: ResumeTemplate) {
  return typeof template.layout?.license === 'string' ? template.layout.license : ''
}

function TemplatePreviewArt({ template, templates }: { template: ResumeTemplate; templates: ResumeTemplate[] }) {
  const base = templateBaseId(template.id, templates)
  const accent = templateAccent(template)
  const line = 'h-1 rounded-full bg-[#D9E1EA]'
  const section = (key: string, rows = 3) => (
    <div key={key} className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: accent }} />
        <span className="h-1.5 w-14 rounded-full" style={{ backgroundColor: accent }} />
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="grid grid-cols-[1fr_34px] gap-2">
          <span className={cn(line, index === rows - 1 && 'w-4/5')} />
          <span className="h-1 rounded-full bg-[#EEF2F6]" />
        </div>
      ))}
    </div>
  )

  if (base === 'compact-two-column') {
    return (
      <div className="h-full w-full bg-white p-3">
        <div className="grid h-full grid-cols-[58px_1fr] gap-3">
          <aside className="flex flex-col items-center gap-2 rounded-[6px] p-2 text-white" style={{ backgroundColor: accent }}>
            <div className="h-10 w-10 rounded-[6px] bg-white/90" />
            <div className="mt-1 h-1 w-9 rounded-full bg-white/80" />
            <div className="h-1 w-7 rounded-full bg-white/60" />
            <div className="mt-3 space-y-1.5 self-stretch">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="h-1 rounded-full bg-white/65" />
              ))}
            </div>
            <div className="mt-auto flex flex-wrap gap-1">
              {Array.from({ length: 4 }).map((_, index) => (
                <span key={index} className="h-3 w-5 rounded-full bg-white/80" />
              ))}
            </div>
          </aside>
          <main className="space-y-3 overflow-hidden pt-1">
            <div>
              <div className="mb-1 h-1 w-20 rounded-full" style={{ backgroundColor: accent }} />
              <div className="h-1 w-32 rounded-full bg-[#C8D4E0]" />
            </div>
            {section('education', 3)}
            {section('project', 5)}
            {section('award', 2)}
          </main>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full w-full bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-[#D8E0E8] pb-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 h-1 w-20 rounded-full" style={{ backgroundColor: accent }} />
          <div className="mb-1 h-1 w-28 rounded-full bg-[#C8D4E0]" />
          <div className="h-1 w-40 rounded-full bg-[#EEF2F6]" />
        </div>
        <div className="h-12 w-10 rounded-[6px] bg-[#E9EEF4]" />
      </div>
      <div className="space-y-3">
        {section('education', 3)}
        {section('project', 5)}
        {section('skill', 2)}
        {section('self', 3)}
      </div>
    </div>
  )
}

function TemplateGalleryCard({
  template,
  templates,
  deleting,
  onDelete,
}: {
  template: ResumeTemplate
  templates: ResumeTemplate[]
  deleting: boolean
  onDelete: (template: ResumeTemplate) => void
}) {
  const base = templateBaseId(template.id, templates)
  const accent = templateAccent(template)
  return (
    <div className="group overflow-hidden rounded-[8px] border border-card-border bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md">
      <div className="bg-[#F3F6F8] p-4">
        <div className="mx-auto aspect-[210/297] max-h-[360px] w-full max-w-[230px] overflow-hidden rounded-[8px] border border-[#DDE5EC] bg-white shadow-sm">
          {template.preview_path ? (
            <img src={template.preview_path} alt={`${template.name} 模板预览`} className="h-full w-full object-cover object-top" loading="lazy" />
          ) : (
            <TemplatePreviewArt template={template} templates={templates} />
          )}
        </div>
      </div>
      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-base font-black text-foreground">{template.name}</div>
            <div className="mt-1 text-xs text-muted">{templateTypeLabel(template, base)} · {base === 'compact-two-column' ? '左右分栏' : '经典单栏'}</div>
          </div>
          {template.source_type !== 'builtin' && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => onDelete(template)}
              disabled={deleting}
              title="删除模板"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-[6px] bg-[#EEF8F3] px-2 py-1 text-xs font-bold text-[#1D7A52]">{template.source_type === 'builtin' ? '内置模板' : '用户导入'}</span>
          <span className="rounded-[6px] bg-[#F4F6F8] px-2 py-1 text-xs font-bold text-muted">A4 预览</span>
          {templateLicenseLabel(template) && (
            <span className="rounded-[6px] bg-[#F4F6F8] px-2 py-1 text-xs font-bold text-muted">{templateLicenseLabel(template)}</span>
          )}
          <span className="rounded-[6px] px-2 py-1 text-xs font-bold text-white" style={{ backgroundColor: accent }}>主题色</span>
        </div>
      </div>
    </div>
  )
}

function previewProfile(version?: ResumeVersion) {
  return version?.profile_snapshot?.profile || PROFILE_EMPTY
}

function previewSections(version?: ResumeVersion) {
  if (!version?.profile_snapshot?.sections) return []
  const selectedSectionIds = version.selected_section_ids?.length
    ? version.selected_section_ids
    : version.profile_snapshot.selected_section_ids || []
  const selectedEntryIds = version.selected_entry_ids?.length
    ? version.selected_entry_ids
    : version.profile_snapshot.selected_entry_ids || []
  const selectedMaterialIds = version.selected_material_ids?.length
    ? version.selected_material_ids
    : version.profile_snapshot.selected_material_ids || []

  return version.profile_snapshot.sections
    .filter(section => !selectedSectionIds.length || selectedSectionIds.includes(section.id))
    .map(section => ({
      ...section,
      entries: (section.entries || [])
        .filter(entry => !selectedEntryIds.length || selectedEntryIds.includes(entry.id))
        .map(entry => ({
          ...entry,
          materials: (entry.materials || []).filter(material => !selectedMaterialIds.length || selectedMaterialIds.includes(material.id)),
        }))
        .filter(entry => entry.description || entry.materials.length),
    }))
    .filter(section => section.summary || section.entries.length)
}

function splitPreviewPages(sections: ResumeSection[]) {
  const pages: ResumeSection[][] = []
  let current: ResumeSection[] = []
  let units = 0
  const limit = 18
  for (const section of sections) {
    const sectionUnits = 2 + section.entries.reduce((sum, entry) => sum + 2 + Math.max(1, entry.materials.length), 0)
    if (current.length && units + sectionUnits > limit) {
      pages.push(current)
      current = []
      units = 0
    }
    current.push(section)
    units += sectionUnits
  }
  if (current.length) pages.push(current)
  return pages.length ? pages : [[]]
}

function sectionTitle(section: ResumeSection) {
  const known = SECTION_KINDS.find(kind => kind.type === section.section_type)
  return section.title || known?.title || '自定义模块'
}

function entryFieldLabels(sectionType: string) {
  if (sectionType === 'academic') {
    return {
      title: '成果名称',
      organization: '期刊 / 会议 / 专利类型',
      role: '作者情况',
      startDate: '发表 / 投稿时间',
      endDate: '状态',
      description: '补充说明',
    }
  }
  if (sectionType === 'campus') {
    return { title: '经历名称', organization: '组织 / 单位', role: '角色', startDate: '开始时间', endDate: '结束时间', description: '经历说明' }
  }
  if (sectionType === 'award') {
    return { title: '荣誉名称', organization: '颁发单位', role: '级别', startDate: '时间', endDate: '状态', description: '补充说明' }
  }
  if (sectionType === 'skill') {
    return { title: '技能 / 证书名称', organization: '发证机构 / 技术方向', role: '熟练度', startDate: '取得时间', endDate: '有效期', description: '说明' }
  }
  if (sectionType === 'self_evaluation') {
    return { title: '评价标题', organization: '', role: '', startDate: '', endDate: '', description: '综合评价内容' }
  }
  return { title: '名称', organization: '机构 / 公司 / 项目方', role: '角色', startDate: '开始时间', endDate: '结束时间', description: '经历概述' }
}

function entryFieldVisibility(sectionType: string) {
  if (sectionType === 'self_evaluation') {
    return { organization: false, role: false, dates: false, endDate: false, description: true }
  }
  if (sectionType === 'skill') {
    return { organization: false, role: false, dates: false, endDate: false, description: false }
  }
  return { organization: true, role: true, dates: true, endDate: sectionType !== 'award', description: true }
}

function entryMetadataValue(entry: ResumeEntry, key: string) {
  return valueOf(entry.metadata || {}, key)
}

function entryMetaText(sectionType: string, entry: ResumeEntry) {
  if (sectionType === 'academic') {
    return [
      entry.organization,
      entry.role,
      entryMetadataValue(entry, 'indexing'),
    ].filter(Boolean).join(' · ')
  }
  return [entry.organization, entry.role].filter(Boolean).join(' · ')
}

function cleanEntryDraftForSave(sectionType: string, draft: ResumeEntry): ResumeEntry {
  if (sectionType !== 'self_evaluation') return draft
  return {
    ...draft,
    organization: '',
    role: '',
    start_date: '',
    end_date: '',
  }
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    cache: 'no-store',
    headers: options?.body ? { 'Content-Type': 'application/json', ...(options.headers || {}) } : options?.headers,
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data?.error || '请求失败')
  return data
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <label className="space-y-2">
      <span className="text-xs font-black text-muted">{label}</span>
      <Input type={type} value={value} placeholder={placeholder} onChange={event => onChange(event.target.value)} />
    </label>
  )
}

function looksLikeHtml(value: string) {
  return /<\/?[a-z][\s\S]*>/i.test(value)
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function textToRichHtml(value: string) {
  const text = String(value || '')
  if (!text.trim()) return ''
  if (looksLikeHtml(text)) return text
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map(line => line.trim() ? `<div>${escapeHtml(line)}</div>` : '<div><br></div>')
    .join('')
}

function sanitizeRichHtml(value: string) {
  const raw = String(value || '')
  if (!raw.trim()) return ''
  if (typeof window === 'undefined' || typeof DOMParser === 'undefined') {
    return escapeHtml(raw)
  }
  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div>${raw}</div>`, 'text/html')
  const allowedTags = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'A', 'OL', 'UL', 'LI', 'DIV', 'P', 'BR', 'SPAN', 'IMG', 'H2', 'H3', 'FONT'])
  const allowedStyles = new Set(['color', 'font-size', 'text-align'])
  const cleanNode = (node: Node) => {
    Array.from(node.childNodes).forEach(child => {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const element = child as HTMLElement
        if (!allowedTags.has(element.tagName)) {
          element.replaceWith(doc.createTextNode(element.textContent || ''))
          return
        }
        Array.from(element.attributes).forEach(attr => {
          const name = attr.name.toLowerCase()
          const value = attr.value
          if (name === 'style') {
            const safeStyle = value
              .split(';')
              .map(part => part.trim())
              .filter(part => {
                const [property, rawValue = ''] = part.split(':').map(item => item.trim().toLowerCase())
                if (!allowedStyles.has(property)) return false
                if (/[<>()]/.test(rawValue)) return false
                if (property === 'font-size') return /^\d{1,2}px$/.test(rawValue) || /^[1-7]$/.test(rawValue)
                if (property === 'text-align') return ['left', 'center', 'right', 'justify'].includes(rawValue)
                return /^#[0-9a-f]{3,8}$/.test(rawValue) || /^[a-z]+$/.test(rawValue) || /^rgb(a)?\([\d\s,.%]+\)$/.test(rawValue)
              })
              .join('; ')
            if (safeStyle) element.setAttribute('style', safeStyle)
            else element.removeAttribute('style')
            return
          }
          if (element.tagName === 'A' && name === 'href') {
            if (/^(https?:|mailto:|#)/i.test(value)) element.setAttribute('target', '_blank')
            else element.removeAttribute('href')
            return
          }
          if (element.tagName === 'IMG' && ['src', 'alt'].includes(name)) {
            if (name === 'src' && !/^(https?:|data:image\/)/i.test(value)) element.removeAttribute('src')
            return
          }
          if (element.tagName === 'FONT' && ['color', 'size'].includes(name)) return
          element.removeAttribute(attr.name)
        })
        cleanNode(element)
      }
    })
  }
  cleanNode(doc.body)
  return doc.body.firstElementChild?.innerHTML || ''
}

function richTextPlain(value: string) {
  const html = sanitizeRichHtml(textToRichHtml(value))
  if (!html) return ''
  if (typeof document === 'undefined') {
    return html.replace(/<[^>]+>/g, '')
  }
  const element = document.createElement('div')
  element.innerHTML = html
  return element.textContent || ''
}

function RichText({ value, className }: { value: string; className?: string }) {
  const html = sanitizeRichHtml(textToRichHtml(value))
  if (!html) return null
  return <div className={cn('rich-text-content', className)} dangerouslySetInnerHTML={{ __html: html }} />
}

function TextArea({
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  rows?: number
}) {
  const editorRef = useRef<HTMLDivElement | null>(null)
  const selectionRef = useRef<Range | null>(null)
  const colorInputRef = useRef<HTMLInputElement | null>(null)
  const editorHtml = sanitizeRichHtml(textToRichHtml(value))
  const saveSelection = () => {
    const editor = editorRef.current
    const selection = window.getSelection()
    if (!editor || !selection || !selection.rangeCount) return
    const range = selection.getRangeAt(0)
    if (editor.contains(range.commonAncestorContainer)) {
      selectionRef.current = range.cloneRange()
    }
  }
  const restoreSelection = () => {
    const selection = window.getSelection()
    const range = selectionRef.current
    if (!selection || !range) return
    selection.removeAllRanges()
    selection.addRange(range)
  }
  const syncEditor = () => {
    const editor = editorRef.current
    if (!editor) return
    const html = sanitizeRichHtml(editor.innerHTML)
    onChange(html)
  }
  const runCommand = (command: string, commandValue?: string) => {
    const editor = editorRef.current
    if (!editor) return
    editor.focus()
    restoreSelection()
    document.execCommand(command, false, commandValue)
    syncEditor()
    saveSelection()
  }
  const insertLink = () => {
    const href = window.prompt('请输入链接地址')
    if (!href) return
    runCommand('createLink', href)
  }
  const insertImage = () => {
    const src = window.prompt('请输入图片链接')
    if (!src) return
    runCommand('insertImage', src)
  }

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    const current = sanitizeRichHtml(editor.innerHTML)
    if (current !== editorHtml) {
      editor.innerHTML = editorHtml
    }
  }, [editorHtml])

  const toolbarButtonClass = 'flex h-8 w-8 items-center justify-center rounded-[6px] text-muted transition hover:bg-white hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35'
  return (
    <div className="space-y-2">
      <div className="space-y-2">
        <span className="text-xs font-black text-muted">{label}</span>
        <div className="flex min-h-10 flex-wrap items-center gap-1 rounded-[8px] border border-card-border bg-[#F7F7F8] px-2 py-1">
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('undo')} title="撤销">
            <Undo2 className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('redo')} title="恢复">
            <Redo2 className="h-4 w-4" />
          </button>
          <div className="mx-1 h-5 w-px bg-card-border" />
          <label className="flex h-8 items-center gap-1 rounded-[6px] px-2 text-xs font-bold text-muted hover:bg-white hover:text-foreground" title="字体大小">
            <ALargeSmall className="h-4 w-4" />
            <select
              className="bg-transparent text-xs font-bold outline-none"
              defaultValue=""
              onMouseDown={saveSelection}
              onChange={event => {
                if (event.target.value) runCommand('fontSize', event.target.value)
                event.target.value = ''
              }}
            >
              <option value="">字号</option>
              <option value="2">12</option>
              <option value="3">14</option>
              <option value="4">16</option>
              <option value="5">18</option>
              <option value="6">20</option>
            </select>
          </label>
          <button type="button" className={toolbarButtonClass} onMouseDown={saveSelection} onClick={() => colorInputRef.current?.click()} title="文字颜色">
            <span className="border-b-2 border-[#111] px-0.5 text-sm font-black leading-none">A</span>
          </button>
          <input ref={colorInputRef} type="color" className="sr-only" onChange={event => runCommand('foreColor', event.target.value)} />
          <button type="button" className={cn(toolbarButtonClass, 'text-primary hover:text-primary')} onClick={() => runCommand('bold')} title="加粗">
            <Bold className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('italic')} title="斜体">
            <Italic className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('underline')} title="下划线">
            <Underline className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={insertLink} title="插入链接">
            <Link className="h-4 w-4" />
          </button>
          <div className="mx-1 h-5 w-px bg-card-border" />
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('insertOrderedList')} title="有序列表">
            <ListOrdered className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('insertUnorderedList')} title="无序列表">
            <List className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('justifyLeft')} title="左对齐">
            <AlignLeft className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={insertImage} title="插入图片">
            <ImageIcon className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('removeFormat')} title="清除格式">
            <RemoveFormatting className="h-4 w-4" />
          </button>
          <button type="button" className={toolbarButtonClass} onClick={() => runCommand('formatBlock', 'h2')} title="小标题">
            <Heading2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder || ''}
        onInput={syncEditor}
        onBlur={() => {
          saveSelection()
          syncEditor()
        }}
        onKeyUp={saveSelection}
        onMouseUp={saveSelection}
        className="rich-text-editor w-full overflow-auto rounded-md border border-card-border bg-white px-3 py-2 text-sm leading-6 text-foreground empty:before:content-[attr(data-placeholder)] empty:before:text-muted/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        style={{ minHeight: `${Math.max(rows, 2) * 1.5 + 1.25}rem` }}
      />
    </div>
  )
}

function EmptyPanel({ children }: { children: string }) {
  return (
    <div className="rounded-[8px] border border-dashed border-card-border bg-[#FFFCFA] px-4 py-6 text-center text-sm text-muted">
      {children}
    </div>
  )
}

function StatusMessage({ error, message }: { error: string; message: string }) {
  if (!error && !message) return null
  return (
    <div
      className={cn(
        'rounded-[8px] border px-4 py-3 text-sm',
        error ? 'border-red-100 bg-red-50 text-red-700' : 'border-emerald-100 bg-emerald-50 text-emerald-700'
      )}
    >
      {error || message}
    </div>
  )
}

function importDraftStats(draft: ResumeImportDraft) {
  return {
    education: draft.profile.education?.length || 0,
    skills: draft.profile.skills?.length || 0,
    sections: draft.sections.length,
    entries: draft.sections.reduce((sum, section) => sum + section.entries.length, 0),
    materials: draft.sections.reduce((sum, section) => sum + section.entries.reduce((entrySum, entry) => entrySum + entry.materials.length, 0), 0),
  }
}

function ImportOldResumeCard({
  importing,
  onImport,
}: {
  importing: boolean
  onImport: (file: File) => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <CardTitle className="text-base font-black text-foreground">导入旧简历内容</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-5 pt-0">
        <p className="text-sm leading-6 text-muted">
          上传 Markdown、Word 或 PDF，系统先解析成草稿，确认后再追加到资料库。
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.docx,.pdf"
          className="hidden"
          onChange={event => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) void onImport(file)
          }}
        />
        <Button type="button" className="w-full" variant="secondary" onClick={() => inputRef.current?.click()} disabled={importing}>
          <Upload className="mr-2 h-4 w-4" />
          {importing ? '解析中...' : '选择旧简历'}
        </Button>
      </CardContent>
    </Card>
  )
}

function ImportPreviewDialog({
  draft,
  confirming,
  onDraftChange,
  onCancel,
  onConfirm,
}: {
  draft: ResumeImportDraft | null
  confirming: boolean
  onDraftChange: (draft: ResumeImportDraft) => void
  onCancel: () => void
  onConfirm: () => Promise<void>
}) {
  if (!draft) return null
  const basics = draft.profile.basics || {}
  const contacts = draft.profile.contacts || {}
  const stats = importDraftStats(draft)
  const updateProfileList = (key: 'education' | 'skills', index: number) => {
    onDraftChange({
      ...draft,
      profile: {
        ...draft.profile,
        [key]: (draft.profile[key] || []).filter((_, itemIndex) => itemIndex !== index),
      },
    })
  }
  const removeSection = (sectionIndex: number) => {
    onDraftChange({ ...draft, sections: draft.sections.filter((_, index) => index !== sectionIndex) })
  }
  const removeEntry = (sectionIndex: number, entryIndex: number) => {
    onDraftChange({
      ...draft,
      sections: draft.sections.map((section, index) => index === sectionIndex
        ? { ...section, entries: section.entries.filter((_, itemIndex) => itemIndex !== entryIndex) }
        : section).filter(section => section.entries.length > 0),
    })
  }
  const removeMaterial = (sectionIndex: number, entryIndex: number, materialIndex: number) => {
    onDraftChange({
      ...draft,
      sections: draft.sections.map((section, index) => index === sectionIndex
        ? {
            ...section,
            entries: section.entries.map((entry, itemIndex) => itemIndex === entryIndex
              ? { ...entry, materials: entry.materials.filter((_, matIndex) => matIndex !== materialIndex) }
              : entry),
          }
        : section),
    })
  }
  const removePhotoCandidate = () => {
    onDraftChange({ ...draft, photo_candidate: null })
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[88vh] w-full max-w-4xl overflow-y-auto rounded-[8px] border border-card-border bg-white shadow-2xl">
        <div className="sticky top-0 flex flex-wrap items-center justify-between gap-3 border-b border-card-border bg-white px-5 py-4">
          <div>
            <h3 className="text-lg font-black text-foreground">确认导入旧简历</h3>
            <p className="mt-1 text-xs text-muted">{draft.source_filename}</p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onCancel} disabled={confirming}>取消</Button>
            <Button type="button" onClick={() => void onConfirm()} disabled={confirming || (!stats.education && !stats.skills && !stats.entries && !stats.materials)}>
              <Upload className="mr-2 h-4 w-4" />
              {confirming ? '导入中...' : '确认导入'}
            </Button>
          </div>
        </div>
        <div className="grid gap-4 p-5 lg:grid-cols-[280px_1fr]">
          <aside className="space-y-3">
            <div className="rounded-[8px] border border-card-border bg-[#FFFCFA] p-4">
              <div className="text-sm font-black text-foreground">解析结果</div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <span className="text-muted">教育背景</span><span className="font-black">{stats.education}</span>
                <span className="text-muted">模块</span><span className="font-black">{stats.sections}</span>
                <span className="text-muted">经历</span><span className="font-black">{stats.entries}</span>
                <span className="text-muted">素材</span><span className="font-black">{stats.materials}</span>
              </div>
            </div>
            {draft.profile.education.length > 0 && (
              <div className="rounded-[8px] border border-card-border bg-white p-4 text-sm">
                <div className="font-black text-foreground">教育背景</div>
                <div className="mt-3 space-y-2">
                  {draft.profile.education.map((item, index) => (
                    <div key={`edu-${index}`} className="flex items-start justify-between gap-2 rounded-md bg-[#FFFCFA] px-3 py-2">
                      <span className="leading-5">{[valueOf(item, 'school'), valueOf(item, 'major'), valueOf(item, 'degree')].filter(Boolean).join(' · ') || '教育背景'}</span>
                      <button type="button" onClick={() => updateProfileList('education', index)} className="text-muted hover:text-danger" title="不导入这条教育背景">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="rounded-[8px] border border-card-border bg-white p-4 text-sm">
              <div className="font-black text-foreground">基本信息</div>
              <div className="mt-3 space-y-2">
                <div><span className="text-muted">姓名：</span>{valueOf(basics, 'name') || '未识别'}</div>
                <div><span className="text-muted">性别：</span>{valueOf(basics, 'gender') || '未识别'}</div>
                <div><span className="text-muted">出生日期：</span>{valueOf(basics, 'birth_date') || '未识别'}</div>
                <div><span className="text-muted">籍贯：</span>{valueOf(basics, 'native_place') || '未识别'}</div>
                <div><span className="text-muted">电话：</span>{valueOf(contacts, 'phone') || '未识别'}</div>
                <div><span className="text-muted">邮箱：</span>{valueOf(contacts, 'email') || '未识别'}</div>
                <div><span className="text-muted">政治面貌：</span>{valueOf(basics, 'political_status') || '未识别'}</div>
              </div>
            </div>
            {draft.photo_candidate?.image_url && (
              <div className="rounded-[8px] border border-card-border bg-white p-4 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-black text-foreground">简历照片</div>
                  <button
                    type="button"
                    onClick={removePhotoCandidate}
                    className="rounded-md p-1 text-muted hover:bg-red-50 hover:text-danger"
                    title="这次不导入照片"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <img
                    src={draft.photo_candidate.image_url}
                    alt="识别到的简历照片"
                    className="h-20 w-16 rounded-md border border-card-border object-cover"
                  />
                  <div className="min-w-0 text-xs leading-5 text-muted">
                    <div className="font-bold text-foreground">确认导入后会设为简历中心照片</div>
                    <div>{draft.photo_candidate.mime_type} · {formatFileSize(draft.photo_candidate.file_size)}</div>
                  </div>
                </div>
              </div>
            )}
            {!!draft.warnings.length && (
              <div className="rounded-[8px] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                <div className="font-black">需要人工检查</div>
                <ul className="mt-2 list-disc space-y-1 pl-4">
                  {draft.warnings.map(item => <li key={item}>{item}</li>)}
                </ul>
              </div>
            )}
          </aside>
          <section className="space-y-4">
            <div className="rounded-[8px] border border-card-border bg-white p-4">
              <div className="text-sm font-black text-foreground">将导入的经历</div>
              <div className="mt-3 space-y-3">
                {!draft.sections.length && <EmptyPanel>未识别到项目、实习、科研等经历模块。</EmptyPanel>}
                {draft.sections.map((section, sectionIndex) => (
                  <div key={section.title} className="rounded-[8px] border border-card-border bg-[#FFFCFA] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-black text-foreground">{section.title}</div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted">{section.entries.length} 条经历</span>
                        <button type="button" onClick={() => removeSection(sectionIndex)} className="rounded-md p-1 text-muted hover:bg-red-50 hover:text-danger" title="不导入这个模块">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <div className="mt-2 space-y-2">
                      {section.entries.map((entry, entryIndex) => (
                        <div key={`${section.title}-${entry.title}`} className="rounded-md bg-white px-3 py-2 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-bold text-foreground">{entry.title}</div>
                            <button type="button" onClick={() => removeEntry(sectionIndex, entryIndex)} className="text-muted hover:text-danger" title="不导入这段经历">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                          <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted">
                            {richTextPlain(entry.description) || entry.materials.map(item => richTextPlain(item.content)).filter(Boolean).join('；')}
                          </div>
                          {!!entry.materials.length && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {entry.materials.map((material, materialIndex) => (
                                <button
                                  key={`${entry.title}-${material.content}-${materialIndex}`}
                                  type="button"
                                  onClick={() => removeMaterial(sectionIndex, entryIndex, materialIndex)}
                                  className="rounded-md border border-card-border px-2 py-1 text-left text-[11px] leading-4 text-muted hover:border-red-200 hover:bg-red-50 hover:text-danger"
                                  title="点击后不导入这条素材"
                                >
                                  {richTextPlain(material.content) || material.content}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function TemplateImportCard({
  importing,
  onImport,
}: {
  importing: boolean
  onImport: (file: File) => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <CardTitle className="text-base font-black text-foreground">导入用户模板</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-5 pt-0">
        <p className="text-sm leading-6 text-muted">
          上传 DOCX、PDF 或 Markdown，先生成模板草稿，确认后保存为可选模板。
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.docx,.pdf"
          className="hidden"
          onChange={event => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) void onImport(file)
          }}
        />
        <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()} disabled={importing}>
          <Upload className="mr-2 h-4 w-4" />
          {importing ? '解析中...' : '选择模板文件'}
        </Button>
      </CardContent>
    </Card>
  )
}

function TemplateImportDialog({
  draft,
  confirming,
  onNameChange,
  onBaseChange,
  onCancel,
  onConfirm,
}: {
  draft: TemplateImportDraft | null
  confirming: boolean
  onNameChange: (name: string) => void
  onBaseChange: (base: string) => void
  onCancel: () => void
  onConfirm: () => Promise<void>
}) {
  if (!draft) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-[8px] border border-card-border bg-white shadow-2xl">
        <div className="sticky top-0 flex flex-wrap items-center justify-between gap-3 border-b border-card-border bg-white px-5 py-4">
          <div>
            <h3 className="text-lg font-black text-foreground">确认保存模板</h3>
            <p className="mt-1 text-xs text-muted">{draft.source_filename}</p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onCancel} disabled={confirming}>取消</Button>
            <Button type="button" onClick={() => void onConfirm()} disabled={confirming || !draft.name.trim()}>
              <Save className="mr-2 h-4 w-4" />
              {confirming ? '保存中...' : '保存模板'}
            </Button>
          </div>
        </div>
        <div className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="模板名称" value={draft.name} onChange={onNameChange} />
            <label className="space-y-2">
              <span className="text-xs font-black text-muted">基础布局</span>
              <Select value={draft.base_template} onChange={event => onBaseChange(event.target.value)}>
                <option value="classic-single">经典单栏</option>
                <option value="compact-two-column">简洁双栏</option>
              </Select>
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            <InfoPill label="模块" value={String(draft.detected.sections)} />
            <InfoPill label="条目" value={String(draft.detected.bullets)} />
            <InfoPill label="短行" value={String(draft.detected.short_lines)} />
            <InfoPill label="联系信息" value={String(draft.detected.contacts)} />
          </div>
          {!!draft.warnings.length && (
            <div className="rounded-[8px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {draft.warnings.join('；')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-card-border bg-[#FFFCFA] p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-lg font-black text-foreground">{value}</div>
    </div>
  )
}

function MaterialEditor({
  material,
  onSave,
  onDelete,
  contentLabel = '素材内容',
  saveLabel = '保存素材',
  visibleLabel = '显示在可选素材中',
  hiddenLabel = '已隐藏',
}: {
  material: ResumeMaterial
  onSave: (material: ResumeMaterial, patch: Partial<ResumeMaterial>) => Promise<void>
  onDelete: (materialId: string) => Promise<void>
  contentLabel?: string
  saveLabel?: string
  visibleLabel?: string
  hiddenLabel?: string
}) {
  const [content, setContent] = useState(material.content)

  useEffect(() => setContent(material.content), [material.content])

  return (
    <div className="rounded-[8px] border border-card-border bg-[#FFFCFA] p-3">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <TextArea label={contentLabel} rows={3} value={content} onChange={setContent} />
        </div>
        <div className="flex flex-col gap-2">
          <Button type="button" size="icon" variant="ghost" onClick={() => onSave(material, { visible: !material.visible })} title={material.visible ? '隐藏素材' : '显示素材'}>
            {material.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          </Button>
          <Button type="button" size="icon" variant="ghost" onClick={() => onDelete(material.id)} title="删除素材">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-xs text-muted">{material.visible ? visibleLabel : hiddenLabel}</span>
        <Button type="button" size="sm" variant="secondary" onClick={() => onSave(material, { content })} disabled={content.trim() === material.content.trim()}>
          <Save className="mr-2 h-3.5 w-3.5" />
          {saveLabel}
        </Button>
      </div>
    </div>
  )
}

function EducationEditor({
  education,
  onChange,
}: {
  education: JsonRecord[]
  onChange: (education: JsonRecord[]) => void
}) {
  const update = (index: number, key: string, value: string) => {
    onChange(education.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  }
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= education.length) return
    const next = [...education]
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChange(next)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-black text-foreground">教育背景</h3>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => onChange([...education, { school: '', major: '', degree: '', start_date: '', end_date: '', detail: '' }])}
        >
          <Plus className="mr-2 h-3.5 w-3.5" />
          新增教育
        </Button>
      </div>
      {!education.length && <EmptyPanel>还没有教育背景。</EmptyPanel>}
      {education.map((item, index) => (
        <div key={index} className="rounded-[8px] border border-card-border bg-white p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-black text-muted">教育背景 {index + 1}</div>
            <div className="flex gap-2">
              <Button type="button" size="icon" variant="ghost" onClick={() => move(index, -1)} disabled={index === 0} title="上移">
                <ChevronUp className="h-4 w-4" />
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={() => move(index, 1)} disabled={index === education.length - 1} title="下移">
                <ChevronDown className="h-4 w-4" />
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={() => onChange(education.filter((_, itemIndex) => itemIndex !== index))} title="删除">
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="学校" value={valueOf(item, 'school')} onChange={value => update(index, 'school', value)} />
            <Field label="专业" value={valueOf(item, 'major')} onChange={value => update(index, 'major', value)} />
            <Field label="学历" value={valueOf(item, 'degree')} onChange={value => update(index, 'degree', value)} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="开始时间" value={valueOf(item, 'start_date')} onChange={value => update(index, 'start_date', value)} />
              <Field label="结束时间" value={valueOf(item, 'end_date')} onChange={value => update(index, 'end_date', value)} />
            </div>
          </div>
          <div className="mt-3">
            <TextArea label="补充说明" rows={3} value={valueOf(item, 'detail')} onChange={value => update(index, 'detail', value)} />
          </div>
        </div>
      ))}
    </div>
  )
}

function EntryEditor({
  entry,
  sectionType,
  index,
  total,
  onSave,
  onDelete,
  onMove,
  onSaveMaterial,
  onDeleteMaterial,
  onReload,
  setError,
  setMessage,
}: {
  entry: ResumeEntry
  sectionType: string
  index: number
  total: number
  onSave: (entryId: string, patch: Partial<ResumeEntry>) => Promise<void>
  onDelete: (entryId: string) => Promise<void>
  onMove: (entry: ResumeEntry, direction: -1 | 1) => Promise<void>
  onSaveMaterial: (material: ResumeMaterial, patch: Partial<ResumeMaterial>) => Promise<void>
  onDeleteMaterial: (materialId: string) => Promise<void>
  onReload: () => Promise<void>
  setError: (value: string) => void
  setMessage: (value: string) => void
}) {
  const [draft, setDraft] = useState(entry)
  const labels = entryFieldLabels(sectionType)
  const visibleFields = entryFieldVisibility(sectionType)
  const canFormatDescription = sectionType === 'project' || sectionType === 'work'
  const updateMetadata = (key: string, value: string) => {
    setDraft(prev => ({ ...prev, metadata: { ...(prev.metadata || {}), [key]: value } }))
  }

  useEffect(() => setDraft(entry), [entry])

  return (
    <div className="rounded-[8px] border border-card-border bg-white p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-black text-foreground">{draft.title || `经历 ${index + 1}`}</div>
          <div className="mt-1 text-xs text-muted">{draft.visible ? '会参与简历组装' : '已隐藏'}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="icon" variant="ghost" onClick={() => onMove(entry, -1)} disabled={index === 0} title="上移">
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button type="button" size="icon" variant="ghost" onClick={() => onMove(entry, 1)} disabled={index === total - 1} title="下移">
            <ChevronDown className="h-4 w-4" />
          </Button>
          <Button type="button" size="icon" variant="ghost" onClick={() => onSave(entry.id, { visible: !entry.visible })} title={entry.visible ? '隐藏' : '显示'}>
            {entry.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          </Button>
          <Button type="button" size="icon" variant="ghost" onClick={() => onDelete(entry.id)} title="删除">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {sectionType === 'academic' && (
          <>
            <Field label="成果类型" value={entryMetadataValue(draft, 'result_type')} onChange={value => updateMetadata('result_type', value)} />
            <Field label="收录 / 分区" value={entryMetadataValue(draft, 'indexing')} onChange={value => updateMetadata('indexing', value)} />
          </>
        )}
        <Field label={labels.title} value={draft.title} onChange={value => setDraft(prev => ({ ...prev, title: value }))} />
        {visibleFields.organization && (
          <Field label={labels.organization} value={draft.organization} onChange={value => setDraft(prev => ({ ...prev, organization: value }))} />
        )}
        {visibleFields.role && <Field label={labels.role} value={draft.role} onChange={value => setDraft(prev => ({ ...prev, role: value }))} />}
        {visibleFields.dates && (
          <div className={cn('grid gap-3', visibleFields.endDate ? 'grid-cols-2' : 'grid-cols-1')}>
            <Field label={labels.startDate} value={draft.start_date} onChange={value => setDraft(prev => ({ ...prev, start_date: value }))} />
            {visibleFields.endDate && (
              <Field label={labels.endDate} value={draft.end_date} onChange={value => setDraft(prev => ({ ...prev, end_date: value }))} />
            )}
          </div>
        )}
      </div>
      {visibleFields.description && (
        <div className="mt-3">
          <TextArea label={labels.description} value={draft.description} onChange={value => setDraft(prev => ({ ...prev, description: value }))} />
        </div>
      )}
      {sectionType === 'skill' && !!draft.materials.length && (
        <div className="mt-4 space-y-3">
          <div>
            <div className="text-xs font-black text-muted">具体内容</div>
            <div className="mt-1 text-xs leading-5 text-muted">这些内容来自旧简历解析，可单独修改或删除。</div>
          </div>
          {draft.materials.map(material => (
            <MaterialEditor
              key={material.id}
              material={material}
              onSave={onSaveMaterial}
              onDelete={onDeleteMaterial}
              contentLabel="具体内容"
              saveLabel="保存内容"
              visibleLabel="参与简历组装"
              hiddenLabel="已隐藏"
            />
          ))}
        </div>
      )}
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        {canFormatDescription && (
          <Button type="button" size="sm" variant="secondary" onClick={() => onSave(entry.id, cleanEntryDraftForSave(sectionType, draft))}>
            <Sparkles className="mr-2 h-3.5 w-3.5" />
            整理说明
          </Button>
        )}
        <Button type="button" size="sm" onClick={() => onSave(entry.id, cleanEntryDraftForSave(sectionType, draft))}>
          <Save className="mr-2 h-3.5 w-3.5" />
          保存经历
        </Button>
      </div>
    </div>
  )
}

function SectionEditor({
  kind,
  section,
  onCreate,
  onSaveSection,
  onDeleteSection,
  onReload,
  setError,
  setMessage,
}: {
  kind: SectionKind
  section?: ResumeSection
  onCreate: (kind: SectionKind) => Promise<void>
  onSaveSection: (section: ResumeSection, patch: Partial<ResumeSection>) => Promise<void>
  onDeleteSection: (sectionId: string) => Promise<void>
  onReload: () => Promise<void>
  setError: (value: string) => void
  setMessage: (value: string) => void
}) {
  const Icon = kind.icon
  const [summary, setSummary] = useState(section?.summary || '')

  useEffect(() => setSummary(section?.summary || ''), [section])

  const addEntry = async () => {
    if (!section) return
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/entries', {
        method: 'POST',
        body: JSON.stringify({
          section_id: section.id,
          title: entryFieldLabels(kind.type).title,
          entry_type: kind.type,
          sort_order: section.entries.length * 10,
        }),
      })
      setMessage('经历已新增')
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '新增经历失败')
    }
  }

  const saveEntry = async (entryId: string, patch: Partial<ResumeEntry>) => {
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/entries/${entryId}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      setMessage('经历已保存')
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存经历失败')
    }
  }

  const deleteEntry = async (entryId: string) => {
    if (!window.confirm('确定删除这段经历及其素材吗？')) return
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/entries/${entryId}`, { method: 'DELETE' })
      setMessage('经历已删除')
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除经历失败')
    }
  }

  const deleteAllEntries = async () => {
    if (!section || !section.entries.length) return
    if (!window.confirm(`确定删除「${kind.title}」里的全部 ${section.entries.length} 段内容吗？`)) return
    setError('')
    setMessage('')
    try {
      for (const entry of section.entries) {
        await requestJson(`/api/resume/entries/${entry.id}`, { method: 'DELETE' })
      }
      setMessage(`${kind.title}已清空`)
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '全部删除失败')
      await onReload()
    }
  }

  const moveEntry = async (entry: ResumeEntry, direction: -1 | 1) => {
    if (!section) return
    const sorted = [...section.entries].sort((a, b) => a.sort_order - b.sort_order)
    const index = sorted.findIndex(item => item.id === entry.id)
    const target = index + direction
    if (target < 0 || target >= sorted.length) return
    const targetEntry = sorted[target]
    await saveEntry(entry.id, { sort_order: targetEntry.sort_order })
    await saveEntry(targetEntry.id, { sort_order: entry.sort_order })
  }

  const saveMaterial = async (material: ResumeMaterial, patch: Partial<ResumeMaterial>) => {
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/materials/${material.id}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      setMessage('具体内容已保存')
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存具体内容失败')
    }
  }

  const deleteMaterial = async (materialId: string) => {
    if (!window.confirm('确定删除这条具体内容吗？')) return
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/materials/${materialId}`, { method: 'DELETE' })
      setMessage('具体内容已删除')
      await onReload()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除具体内容失败')
    }
  }

  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-[#FFF0E5] text-primary">
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-base font-black text-foreground">{kind.title}</CardTitle>
              <p className="mt-1 text-xs text-muted">{section ? `${section.entries.length} 段经历` : '尚未创建'}</p>
            </div>
          </div>
          {section ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted">显示</span>
              <Switch checked={section.visible} onChange={checked => onSaveSection(section, { visible: checked })} />
              <Button type="button" size="sm" variant="secondary" onClick={addEntry}>
                <Plus className="mr-2 h-3.5 w-3.5" />
                新增经历
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={() => onDeleteSection(section.id)} title="删除板块">
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <Button type="button" size="sm" variant="secondary" onClick={() => onCreate(kind)}>
              <Plus className="mr-2 h-3.5 w-3.5" />
              创建板块
            </Button>
          )}
        </div>
      </CardHeader>
      {section && (
        <CardContent className="space-y-4 p-5 pt-0">
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <TextArea label="板块说明" value={summary} onChange={setSummary} rows={2} />
            <div className="flex flex-wrap items-end gap-2">
              <Button type="button" variant="secondary" onClick={() => onSaveSection(section, { summary })}>
                <Save className="mr-2 h-3.5 w-3.5" />
                保存说明
              </Button>
              <Button type="button" variant="ghost" onClick={deleteAllEntries} disabled={!section.entries.length}>
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                全部删除
              </Button>
            </div>
          </div>
          {!section.entries.length && <EmptyPanel>{kind.emptyText}</EmptyPanel>}
          {[...section.entries].sort((a, b) => a.sort_order - b.sort_order).map((entry, index, entries) => (
            <EntryEditor
              key={entry.id}
              entry={entry}
              sectionType={kind.type}
              index={index}
              total={entries.length}
              onSave={saveEntry}
              onDelete={deleteEntry}
              onMove={moveEntry}
              onSaveMaterial={saveMaterial}
              onDeleteMaterial={deleteMaterial}
              onReload={onReload}
              setError={setError}
              setMessage={setMessage}
            />
          ))}
        </CardContent>
      )}
    </Card>
  )
}

function PhotoPanel({
  photo,
  uploading,
  onUpload,
  onDelete,
}: {
  photo: ResumePhoto | null
  uploading: boolean
  onUpload: (file: File) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <CardTitle className="text-base font-black text-foreground">简历照片</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5 pt-0">
        <div className="flex items-center gap-4">
          <div className="flex h-24 w-20 shrink-0 items-center justify-center overflow-hidden rounded-[8px] border border-card-border bg-[#FFFCFA]">
            {photo?.image_url ? (
              <img src={photo.image_url} alt="简历照片" className="h-full w-full object-cover" />
            ) : (
              <span className="px-3 text-center text-xs text-muted">未上传</span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-black text-foreground">{photo ? '已保存照片' : '可选上传照片'}</div>
            <div className="mt-1 text-xs leading-5 text-muted">
              {photo ? `${photo.mime_type} · ${formatFileSize(photo.file_size)}` : '支持 JPG、PNG、WebP，最大 5MB。'}
            </div>
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={event => {
            const file = event.target.files?.[0]
            if (file) onUpload(file)
            event.currentTarget.value = ''
          }}
        />
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()} disabled={uploading}>
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? '上传中...' : photo ? '替换' : '上传'}
          </Button>
          <Button type="button" variant="ghost" onClick={onDelete} disabled={!photo || uploading}>
            <Trash2 className="mr-2 h-4 w-4" />
            删除
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function VersionNameEditor({
  version,
  onSave,
}: {
  version: ResumeVersion
  onSave: (version: ResumeVersion, patch: Partial<ResumeVersion>) => Promise<void>
}) {
  const [name, setName] = useState(version.name)

  useEffect(() => setName(version.name), [version.name])

  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <Input value={name} onChange={event => setName(event.target.value)} />
      <Button type="button" size="sm" variant="secondary" onClick={() => onSave(version, { name })} disabled={!name.trim() || name.trim() === version.name}>
        重命名
      </Button>
    </div>
  )
}

function VersionBuilder({
  sections,
  templates,
  onCreate,
  onCancel,
}: {
  sections: ResumeSection[]
  templates: ResumeTemplate[]
  onCreate: (payload: {
    name: string
    target_company: string
    target_title: string
    template_id: string
    selected_section_ids: string[]
    selected_entry_ids: string[]
    selected_material_ids: string[]
  }) => Promise<void>
  onCancel: () => void
}) {
  const firstTemplate = templates[0]?.id || ''
  const [name, setName] = useState('我的简历版本')
  const [company, setCompany] = useState('')
  const [title, setTitle] = useState('')
  const [templateId, setTemplateId] = useState(firstTemplate)
  const [sectionIds, setSectionIds] = useState<string[]>(() => sections.filter(section => section.visible).map(section => section.id))
  const [entryIds, setEntryIds] = useState<string[]>(() =>
    sections.flatMap(section => section.visible ? section.entries.filter(entry => entry.visible).map(entry => entry.id) : [])
  )
  const [materialIds, setMaterialIds] = useState<string[]>(() =>
    sections.flatMap(section =>
      section.visible
        ? section.entries.flatMap(entry => entry.visible ? entry.materials.filter(material => material.visible).map(material => material.id) : [])
        : []
    )
  )

  const selectedCount = materialIds.length
  const toggleValue = (values: string[], value: string, checked: boolean) => {
    if (checked) return values.includes(value) ? values : [...values, value]
    return values.filter(item => item !== value)
  }

  const toggleSection = (section: ResumeSection, checked: boolean) => {
    const sectionEntryIds = section.entries.map(entry => entry.id)
    const sectionMaterialIds = section.entries.flatMap(entry => entry.materials.map(material => material.id))
    setSectionIds(prev => toggleValue(prev, section.id, checked))
    setEntryIds(prev => checked ? Array.from(new Set([...prev, ...sectionEntryIds])) : prev.filter(id => !sectionEntryIds.includes(id)))
    setMaterialIds(prev => checked ? Array.from(new Set([...prev, ...sectionMaterialIds])) : prev.filter(id => !sectionMaterialIds.includes(id)))
  }

  const toggleEntry = (section: ResumeSection, entry: ResumeEntry, checked: boolean) => {
    const entryMaterialIds = entry.materials.map(material => material.id)
    if (checked) setSectionIds(prev => toggleValue(prev, section.id, true))
    setEntryIds(prev => toggleValue(prev, entry.id, checked))
    setMaterialIds(prev => checked ? Array.from(new Set([...prev, ...entryMaterialIds])) : prev.filter(id => !entryMaterialIds.includes(id)))
  }

  const toggleMaterial = (section: ResumeSection, entry: ResumeEntry, material: ResumeMaterial, checked: boolean) => {
    if (checked) {
      setSectionIds(prev => toggleValue(prev, section.id, true))
      setEntryIds(prev => toggleValue(prev, entry.id, true))
    }
    setMaterialIds(prev => toggleValue(prev, material.id, checked))
  }

  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base font-black text-foreground">创建简历版本</CardTitle>
            <p className="mt-1 text-xs text-muted">选择本次简历要使用的板块、经历和素材，保存后形成独立快照。</p>
          </div>
          <div className="text-xs font-black text-primary">已选 {sectionIds.length} 个板块 · {entryIds.length} 段经历 · {selectedCount} 条素材</div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-5 pt-0">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="版本名称" value={name} onChange={setName} />
          <Field label="目标公司" value={company} onChange={setCompany} />
          <Field label="目标职位" value={title} onChange={setTitle} />
          <label className="space-y-2">
            <span className="text-xs font-black text-muted">模板</span>
            <Select value={templateId} onChange={event => setTemplateId(event.target.value)}>
              {templates.map(template => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </Select>
          </label>
        </div>

        <div className="space-y-3">
          {!sections.length && <EmptyPanel>请先在“我的资料”里创建经历板块。</EmptyPanel>}
          {sections.map(section => (
            <div key={section.id} className="rounded-[8px] border border-card-border bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-black text-foreground">{section.title}</div>
                  <div className="mt-1 text-xs text-muted">{section.entries.length} 段经历</div>
                </div>
                <Switch checked={sectionIds.includes(section.id)} onChange={checked => toggleSection(section, checked)} />
              </div>
              <div className="mt-4 space-y-3">
                {section.entries.map(entry => (
                  <div key={entry.id} className="rounded-[8px] border border-card-border bg-[#FFFCFA] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-black text-foreground">{entry.title}</div>
                        <div className="mt-1 text-xs text-muted">{entry.materials.length} 条素材</div>
                      </div>
                      <Switch checked={entryIds.includes(entry.id)} onChange={checked => toggleEntry(section, entry, checked)} />
                    </div>
                    {entry.materials.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {entry.materials.map(material => (
                          <label key={material.id} className="flex items-start gap-3 rounded-md bg-white p-3">
                            <input
                              type="checkbox"
                              className="mt-1 h-4 w-4 accent-primary"
                              checked={materialIds.includes(material.id)}
                              onChange={event => toggleMaterial(section, entry, material, event.target.checked)}
                            />
                            <RichText value={material.content} className="text-sm leading-6 text-foreground" />
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>取消</Button>
          <Button
            type="button"
            onClick={() => onCreate({
              name,
              target_company: company,
              target_title: title,
              template_id: templateId,
              selected_section_ids: sectionIds,
              selected_entry_ids: entryIds,
              selected_material_ids: materialIds,
            })}
            disabled={!name.trim() || !templateId}
          >
            <Save className="mr-2 h-4 w-4" />
            保存版本
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ResumePreview({
  version,
  templates,
  photo,
  showPhoto,
  onShowPhotoChange,
  onTemplateChange,
}: {
  version?: ResumeVersion
  templates: ResumeTemplate[]
  photo: ResumePhoto | null
  showPhoto: boolean
  onShowPhotoChange: (value: boolean) => void
  onTemplateChange: (version: ResumeVersion, templateId: string) => Promise<void>
}) {
  if (!version) {
    return (
      <Card className="rounded-[8px] shadow-none">
        <CardContent className="p-6">
          <EmptyPanel>选择一个简历版本后，这里会显示 A4 预览。</EmptyPanel>
        </CardContent>
      </Card>
    )
  }

  const profile = previewProfile(version)
  const sections = previewSections(version)
  const pages = splitPreviewPages(sections)
  const basics = profile.basics || {}
  const contacts = profile.contacts || {}
  const templateId = version.template_id || version.profile_snapshot?.template?.id || templates[0]?.id || 'classic-single'
  const currentTemplate = templates.find(template => template.id === templateId) || version.profile_snapshot?.template || templates[0]
  const accent = currentTemplate ? templateAccent(currentTemplate) : '#2563EB'
  const isTwoColumn = templateBaseId(templateId, templates) === 'compact-two-column'
  const snapshotHasPhoto = Boolean(version.profile_snapshot?.photo)
  const photoUrl = snapshotHasPhoto ? photo?.image_url : ''
  const educationText = (profile.education || [])
    .map(item => [valueOf(item, 'school'), valueOf(item, 'major'), valueOf(item, 'degree')].filter(Boolean).join(' · '))
    .filter(Boolean)
  const personalText = [
    valueOf(basics, 'gender'),
    valueOf(basics, 'birth_date'),
    valueOf(basics, 'native_place'),
    valueOf(basics, 'political_status'),
    ...customFieldsOf(basics).map(item => [item.label, item.value].filter(Boolean).join('：')),
  ].filter(Boolean)
  const contactsText = [
    valueOf(contacts, 'phone'),
    valueOf(contacts, 'email'),
  ].filter(Boolean)
  const targetText = [version.target_company, version.target_title].filter(Boolean).join(' · ')

  const renderEntryBody = (section: ResumeSection, entry: ResumeEntry, className = '') => (
    <div key={entry.id} className={cn('break-inside-avoid', className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-black text-[#1F1F1F]">{entry.title}</div>
        {section.section_type !== 'self_evaluation' && (
          <div className="text-[10px] text-[#686868]">{[entry.start_date, entry.end_date].filter(Boolean).join(' - ')}</div>
        )}
      </div>
      {section.section_type !== 'self_evaluation' && entryMetaText(section.section_type, entry) && (
        <div className="mt-0.5 text-[11px] text-[#555]">{entryMetaText(section.section_type, entry)}</div>
      )}
      {entry.description && <RichText value={entry.description} className="mt-1 text-[11px] leading-5 text-[#3F3F3F]" />}
      {!!entry.materials.length && (
        <ul className="mt-1 space-y-1 pl-4 text-[11px] leading-5 text-[#2F2F2F]">
          {entry.materials.map(material => (
            <li key={material.id} className="list-disc"><RichText value={material.content} /></li>
          ))}
        </ul>
      )}
    </div>
  )

  const renderSection = (section: ResumeSection) => (
    <section key={section.id} className="break-inside-avoid">
      <h3 className={cn('border-b pb-1 font-black text-[#1F1F1F]', isTwoColumn ? 'text-[13px]' : 'text-[15px]')}>
        {sectionTitle(section)}
      </h3>
      {section.summary && <RichText value={section.summary} className="mt-2 text-[11px] leading-5 text-[#3F3F3F]" />}
      <div className="mt-2 space-y-3">
        {section.entries.map(entry => renderEntryBody(section, entry))}
      </div>
    </section>
  )

  const renderSourceHeader = (className = '') => (
    <header className={cn('flex flex-col items-center gap-2 text-center', className)}>
      {showPhoto && photoUrl && <img src={photoUrl} alt="简历照片" className="h-[92px] w-[92px] object-cover" />}
      <div className="space-y-1">
        <h2 className="text-[28px] font-black leading-none text-[#111]">{valueOf(basics, 'name') || '未填写姓名'}</h2>
        {targetText && <div className="text-[12px] leading-5 text-[#333]">{targetText}</div>}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-[11px] leading-5 text-[#333]">
        {valueOf(contacts, 'email') && <span className="inline-flex items-center gap-1"><span style={{ color: accent }}>@</span>{valueOf(contacts, 'email')}</span>}
        {valueOf(contacts, 'phone') && <span className="inline-flex items-center gap-1"><span style={{ color: accent }}>T</span>{valueOf(contacts, 'phone')}</span>}
        {!!personalText.length && <span className="inline-flex items-center gap-1"><span style={{ color: accent }}>I</span>{personalText.join(' · ')}</span>}
      </div>
    </header>
  )

  const renderSourceSkillSection = () => {
    if (!profile.skills.length) return null
    return (
      <section className="break-inside-avoid">
        <h3 className="mb-2 text-[13px] font-black" style={{ color: accent }}>技能证书</h3>
        <div className="space-y-1.5 text-[11px] leading-5">
          {profile.skills.map(skill => (
            <div key={skill} className="border-l-[5px] pl-2" style={{ borderColor: accent }}>{skill}</div>
          ))}
        </div>
      </section>
    )
  }

  const renderSourceEducationSection = () => {
    if (!profile.education.length) return null
    return (
      <section className="break-inside-avoid">
        <h3 className="mb-2 text-[13px] font-black" style={{ color: accent }}>教育背景</h3>
        <div className="space-y-3">
          {profile.education.map((item, index) => (
            <div key={`${valueOf(item, 'school')}-${index}`} className="text-[11px] leading-5">
              <div className="flex items-baseline justify-between gap-3">
                <strong className="text-[#1F1F1F]">{valueOf(item, 'school') || '教育经历'}</strong>
                <span className="text-[10px] text-[#666]">{[valueOf(item, 'start_date'), valueOf(item, 'end_date')].filter(Boolean).join(' - ')}</span>
              </div>
              <div className="text-[#555]">{[valueOf(item, 'major'), valueOf(item, 'degree')].filter(Boolean).join(' · ')}</div>
              {valueOf(item, 'detail') && <RichText value={valueOf(item, 'detail')} className="mt-1 text-[#3F3F3F]" />}
            </div>
          ))}
        </div>
      </section>
    )
  }

  const renderAzurillPage = (pageSections: ResumeSection[], pageIndex: number) => {
    const sidebarSections = pageSections.filter(section => ['skill', 'certificate', 'award', 'self_evaluation'].includes(section.section_type))
    const mainSections = pageSections.filter(section => !['skill', 'certificate', 'award', 'self_evaluation'].includes(section.section_type))
    return (
      <div>
        {pageIndex === 0 && renderSourceHeader('mb-12')}
        <div className="grid grid-cols-[30%_1fr] gap-12">
          <aside className="space-y-6">
            {pageIndex === 0 && renderSourceSkillSection()}
            {sidebarSections.map(section => (
              <section key={section.id} className="break-inside-avoid">
                <h3 className="mb-2 text-[13px] font-black" style={{ color: accent }}>{sectionTitle(section)}</h3>
                <div className="space-y-3">{section.entries.map(entry => renderEntryBody(section, entry, 'text-[11px]'))}</div>
              </section>
            ))}
          </aside>
          <main className="space-y-6">
            {pageIndex === 0 && renderSourceEducationSection()}
            {mainSections.map(section => (
              <section key={section.id} className="break-inside-avoid">
                <h3 className="mb-2 text-[13px] font-black" style={{ color: accent }}>{sectionTitle(section)}</h3>
                {section.summary && <RichText value={section.summary} className="mb-2 text-[11px] leading-5 text-[#3F3F3F]" />}
                <div className="relative space-y-3">
                  <div className="absolute bottom-0 top-0 w-px" style={{ left: 7.5, backgroundColor: accent }} />
                  {section.entries.map(entry => (
                    <div key={entry.id} className="grid grid-cols-[16px_1fr] gap-2 break-inside-avoid">
                      <div className="relative z-10 flex justify-center pt-[10px]">
                        <span className="h-[9px] w-[9px] rounded-full border bg-white" style={{ borderColor: accent }} />
                      </div>
                      <div>{renderEntryBody(section, entry)}</div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </main>
        </div>
      </div>
    )
  }

  const renderBronzorPage = (pageSections: ResumeSection[], pageIndex: number) => (
    <div>
      {pageIndex === 0 && renderSourceHeader('mb-10')}
      <main className="space-y-5">
        {pageIndex === 0 && renderSourceEducationSection()}
        {pageSections.map(section => (
          <section key={section.id} className="grid grid-cols-[30%_1fr] gap-12 border-t pt-3 break-inside-avoid" style={{ borderColor: accent }}>
            <h3 className="text-[12px] font-bold leading-5" style={{ color: accent }}>{sectionTitle(section)}</h3>
            <div>
              {section.summary && <RichText value={section.summary} className="mb-2 text-[11px] leading-5 text-[#3F3F3F]" />}
              <div className="space-y-3">{section.entries.map(entry => renderEntryBody(section, entry))}</div>
            </div>
          </section>
        ))}
        {pageIndex === 0 && profile.skills.length > 0 && (
          <section className="grid grid-cols-[30%_1fr] gap-12 border-t pt-3 break-inside-avoid" style={{ borderColor: accent }}>
            <h3 className="text-[12px] font-bold leading-5" style={{ color: accent }}>技能证书</h3>
            <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-[11px] leading-5">
              {profile.skills.map(skill => <div key={skill}>{skill}</div>)}
            </div>
          </section>
        )}
      </main>
    </div>
  )

  const renderClassicPage = (pageSections: ResumeSection[], pageIndex: number) => (
    <div className="space-y-5">
      {pageIndex === 0 && (
        <header className="flex items-start justify-between gap-6 border-b border-[#D8D8D8] pb-5">
          <div className="min-w-0">
            <h2 className="text-[28px] font-black leading-tight text-[#111]">{valueOf(basics, 'name') || '未填写姓名'}</h2>
            {!!personalText.length && <div className="mt-2 text-[12px] leading-5 text-[#444]">{personalText.join(' · ')}</div>}
            {!!contactsText.length && <div className="mt-1 text-[11px] leading-5 text-[#555]">{contactsText.join(' · ')}</div>}
            {targetText && <div className="mt-1 text-[11px] leading-5 text-[#555]">目标：{targetText}</div>}
          </div>
          {showPhoto && photoUrl && <img src={photoUrl} alt="简历照片" className="h-28 w-24 object-cover" />}
        </header>
      )}
      {pageSections.map(renderSection)}
    </div>
  )

  const renderTwoColumnPage = (pageSections: ResumeSection[], pageIndex: number) => (
    <div className="grid grid-cols-[176px_1fr] gap-6">
      <aside className="space-y-5 border-r border-[#D8D8D8] pr-5">
        {pageIndex === 0 && (
          <>
            {showPhoto && photoUrl && <img src={photoUrl} alt="简历照片" className="h-32 w-28 object-cover" />}
            <div>
              <h2 className="text-[24px] font-black leading-tight text-[#111]">{valueOf(basics, 'name') || '未填写姓名'}</h2>
              {!!personalText.length && <div className="mt-2 text-[11px] leading-5 text-[#555]">{personalText.join(' · ')}</div>}
            </div>
            {!!contactsText.length && (
              <section>
                <h3 className="border-b pb-1 text-[12px] font-black text-[#1F1F1F]">联系方式</h3>
                <div className="mt-2 space-y-1 text-[10px] leading-4 text-[#555]">
                  {contactsText.map(item => <div key={item}>{item}</div>)}
                </div>
              </section>
            )}
            {!!profile.skills.length && (
              <section>
                <h3 className="border-b pb-1 text-[12px] font-black text-[#1F1F1F]">技能证书</h3>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {profile.skills.map(skill => (
                    <span key={skill} className="border border-[#D8D8D8] px-1.5 py-0.5 text-[10px] text-[#333]">{skill}</span>
                  ))}
                </div>
              </section>
            )}
            {!!educationText.length && (
              <section>
                <h3 className="border-b pb-1 text-[12px] font-black text-[#1F1F1F]">教育背景</h3>
                <div className="mt-2 space-y-1 text-[10px] leading-4 text-[#555]">
                  {educationText.map(item => <div key={item}>{item}</div>)}
                </div>
              </section>
            )}
          </>
        )}
      </aside>
      <main className="space-y-5">
        {pageIndex === 0 && targetText && <div className="text-[11px] leading-5 text-[#555]">目标：{targetText}</div>}
        {pageSections.map(renderSection)}
      </main>
    </div>
  )

  return (
    <Card className="rounded-[8px] shadow-none">
      <CardHeader className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base font-black text-foreground">A4 预览</CardTitle>
            <p className="mt-1 text-xs text-muted">{version.name} · {pages.length} 页估算</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-muted">
              显示照片
              <Switch checked={showPhoto} onChange={onShowPhotoChange} disabled={!snapshotHasPhoto || !photoUrl} />
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              <LayoutTemplate className="h-4 w-4" />
              <Select value={templateId} onChange={event => onTemplateChange(version, event.target.value)} className="w-36">
                {templates.map(template => (
                  <option key={template.id} value={template.id}>{template.name}</option>
                ))}
              </Select>
            </label>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-5 pt-0">
        <div className="max-h-[calc(100vh-260px)] overflow-auto rounded-[8px] border border-card-border bg-[#F7F7F8] p-4">
          <div className="flex min-w-[820px] flex-col items-center gap-5">
            {pages.map((pageSections, index) => (
              <div
                key={index}
                className={cn('bg-white text-[#1F1F1F] shadow-sm', templateId === 'reactive-azurill' || templateId === 'reactive-bronzor' ? 'px-12 py-12' : isTwoColumn ? 'px-10 py-10' : 'px-12 py-10')}
                style={{ width: '210mm', minHeight: '297mm' }}
              >
                {templateId === 'reactive-azurill'
                  ? renderAzurillPage(pageSections, index)
                  : templateId === 'reactive-bronzor'
                    ? renderBronzorPage(pageSections, index)
                    : isTwoColumn
                      ? renderTwoColumnPage(pageSections, index)
                      : renderClassicPage(pageSections, index)}
                <div className="mt-8 border-t border-[#E5E5E5] pt-2 text-right text-[10px] text-[#777]">
                  第 {index + 1} 页 / 共 {pages.length} 页
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ResumeCenterPage() {
  const [activeTab, setActiveTab] = useState<typeof tabs[number]['id']>('profile')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [profile, setProfile] = useState<ResumeProfile>(PROFILE_EMPTY)
  const [photo, setPhoto] = useState<ResumePhoto | null>(null)
  const [sections, setSections] = useState<ResumeSection[]>([])
  const [templates, setTemplates] = useState<ResumeTemplate[]>([])
  const [versions, setVersions] = useState<ResumeVersion[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [basics, setBasics] = useState<JsonRecord>({})
  const [contacts, setContacts] = useState<JsonRecord>({})
  const [preferences, setPreferences] = useState<JsonRecord>({})
  const [education, setEducation] = useState<JsonRecord[]>([])
  const [personalCustomFields, setPersonalCustomFields] = useState<PersonalCustomField[]>([])
  const [skillsText, setSkillsText] = useState('')
  const [customTitle, setCustomTitle] = useState('')
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [importingResume, setImportingResume] = useState(false)
  const [confirmingImport, setConfirmingImport] = useState(false)
  const [importDraft, setImportDraft] = useState<ResumeImportDraft | null>(null)
  const [importingTemplate, setImportingTemplate] = useState(false)
  const [confirmingTemplate, setConfirmingTemplate] = useState(false)
  const [templateDraft, setTemplateDraft] = useState<TemplateImportDraft | null>(null)
  const [deletingTemplateId, setDeletingTemplateId] = useState('')
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [usingVersionId, setUsingVersionId] = useState('')
  const [previewPhotoVisible, setPreviewPhotoVisible] = useState(true)

  const applyPayload = (payload: ResumeCenterPayload) => {
    setProfile(payload.profile)
    setPhoto(payload.photo || null)
    setSections(payload.sections || [])
    setTemplates(payload.templates || [])
    setVersions(payload.versions || [])
    setBasics(payload.profile.basics || {})
    setContacts(payload.profile.contacts || {})
    setPreferences(payload.profile.preferences || {})
    setEducation(Array.isArray(payload.profile.education) ? payload.profile.education : [])
    setPersonalCustomFields(customFieldsOf(payload.profile.basics || {}))
    setSkillsText(Array.isArray(payload.profile.skills) ? payload.profile.skills.join('\n') : '')
  }

  const loadCenter = async () => {
    setError('')
    try {
      const payload = await requestJson<ResumeCenterPayload>('/api/resume/center')
      applyPayload(payload)
    } catch (error) {
      setError(error instanceof Error ? error.message : '读取简历中心失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCenter()
  }, [])

  useEffect(() => {
    if (!versions.length) {
      setSelectedVersionId('')
      return
    }
    if (!selectedVersionId || !versions.some(version => version.id === selectedVersionId)) {
      setSelectedVersionId(versions[0].id)
    }
  }, [versions, selectedVersionId])

  const sectionByType = useMemo(() => {
    const map = new Map<string, ResumeSection>()
    for (const section of sections) {
      if (!map.has(section.section_type)) map.set(section.section_type, section)
    }
    return map
  }, [sections])

  const selectedVersion = useMemo(
    () => versions.find(version => version.id === selectedVersionId) || versions[0],
    [selectedVersionId, versions]
  )

  const setBasicField = (key: string, value: string) => setBasics(prev => ({ ...prev, [key]: value }))
  const setContactField = (key: string, value: string) => setContacts(prev => ({ ...prev, [key]: value }))
  const updateCustomField = (index: number, key: keyof PersonalCustomField, value: string) => {
    setPersonalCustomFields(prev => prev.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  }

  const saveProfile = async () => {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const saved = await requestJson<ResumeProfile>('/api/resume/profile', {
        method: 'PUT',
        body: JSON.stringify({
          basics: {
            ...basics,
            custom_fields: personalCustomFields.filter(item => item.label.trim() || item.value.trim()),
          },
          contacts,
          preferences,
          education,
          skills: toLines(skillsText),
        }),
      })
      setProfile(saved)
      setBasics(saved.basics || {})
      setContacts(saved.contacts || {})
      setPreferences(saved.preferences || {})
      setEducation(Array.isArray(saved.education) ? saved.education : [])
      setPersonalCustomFields(customFieldsOf(saved.basics || {}))
      setSkillsText(Array.isArray(saved.skills) ? saved.skills.join('\n') : '')
      setMessage('我的资料已保存')
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存我的资料失败')
    } finally {
      setSaving(false)
    }
  }

  const resetResumeCenter = async () => {
    if (!window.confirm('确定重置简历中心吗？这会删除个人资料、教育背景、全部模块内容、照片、用户模板和简历版本。')) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const data = await requestJson<{ center: ResumeCenterPayload }>('/api/resume/center/reset', { method: 'POST' })
      applyPayload(data.center)
      setSelectedVersionId('')
      setImportDraft(null)
      setTemplateDraft(null)
      setCreatingVersion(false)
      setMessage('简历中心已重置')
    } catch (error) {
      setError(error instanceof Error ? error.message : '重置简历中心失败')
    } finally {
      setSaving(false)
    }
  }

  const createSection = async (kind: SectionKind) => {
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/sections', {
        method: 'POST',
        body: JSON.stringify({
          section_type: kind.type,
          title: kind.title,
          sort_order: SECTION_KINDS.findIndex(item => item.type === kind.type) * 10,
        }),
      })
      setMessage('板块已创建')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '创建板块失败')
    }
  }

  const saveSection = async (section: ResumeSection, patch: Partial<ResumeSection>) => {
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/sections/${section.id}`, {
        method: 'PUT',
        body: JSON.stringify({ ...section, ...patch }),
      })
      setMessage('板块已保存')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存板块失败')
    }
  }

  const deleteSection = async (sectionId: string) => {
    if (!window.confirm('确定删除整个板块及其经历素材吗？')) return
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/sections/${sectionId}`, { method: 'DELETE' })
      setMessage('板块已删除')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除板块失败')
    }
  }

  const addCustomSection = async () => {
    const title = customTitle.trim()
    if (!title) return
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/sections', {
        method: 'POST',
        body: JSON.stringify({
          section_type: 'custom',
          title,
          sort_order: 200 + sections.filter(section => section.section_type === 'custom').length * 10,
        }),
      })
      setCustomTitle('')
      setMessage('自定义模块已新增')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '新增自定义模块失败')
    }
  }

  const uploadPhoto = async (file: File) => {
    setUploadingPhoto(true)
    setError('')
    setMessage('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/resume/photo', { method: 'POST', body: form })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || '上传照片失败')
      setPhoto(data.photo || null)
      setMessage('照片已保存')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '上传照片失败')
    } finally {
      setUploadingPhoto(false)
    }
  }

  const deletePhoto = async () => {
    if (!photo || !window.confirm('确定删除简历照片吗？')) return
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/photo', { method: 'DELETE' })
      setPhoto(null)
      setMessage('照片已删除')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除照片失败')
    }
  }

  const importOldResume = async (file: File) => {
    setImportingResume(true)
    setError('')
    setMessage('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/resume/import-preview', { method: 'POST', body: form })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || '解析旧简历失败')
      setImportDraft(data as ResumeImportDraft)
      setMessage('旧简历已解析，请确认后导入。')
    } catch (error) {
      setError(error instanceof Error ? error.message : '解析旧简历失败')
    } finally {
      setImportingResume(false)
    }
  }

  const confirmImportOldResume = async () => {
    if (!importDraft) return
    setConfirmingImport(true)
    setError('')
    setMessage('')
    try {
      const data = await requestJson<{ imported?: Record<string, number>; photo?: ResumePhoto | null }>('/api/resume/import-confirm', {
        method: 'POST',
        body: JSON.stringify({ draft: importDraft }),
      })
      const imported = data.imported || {}
      setImportDraft(null)
      setMessage(`旧简历已导入：新增 ${imported.entries || 0} 条经历、${imported.materials || 0} 条素材${data.photo ? '，并更新照片' : ''}。`)
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '导入旧简历失败')
    } finally {
      setConfirmingImport(false)
    }
  }

  const importUserTemplate = async (file: File) => {
    setImportingTemplate(true)
    setError('')
    setMessage('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/resume/template-import-preview', { method: 'POST', body: form })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || '解析模板失败')
      setTemplateDraft(data as TemplateImportDraft)
      setMessage('模板草稿已生成，请确认后保存。')
    } catch (error) {
      setError(error instanceof Error ? error.message : '解析模板失败')
    } finally {
      setImportingTemplate(false)
    }
  }

  const confirmImportUserTemplate = async () => {
    if (!templateDraft) return
    setConfirmingTemplate(true)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/template-import-confirm', {
        method: 'POST',
        body: JSON.stringify({ draft: templateDraft }),
      })
      setTemplateDraft(null)
      setMessage('用户模板已保存，可以在创建或预览简历时选择。')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存模板失败')
    } finally {
      setConfirmingTemplate(false)
    }
  }

  const deleteUserTemplate = async (template: ResumeTemplate) => {
    if (template.source_type === 'builtin') return
    if (!window.confirm(`确定删除用户模板「${template.name}」吗？已使用该模板的历史简历版本不会被删除。`)) return
    setDeletingTemplateId(template.id)
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/templates/${template.id}`, { method: 'DELETE' })
      setMessage('用户模板已删除')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除模板失败')
    } finally {
      setDeletingTemplateId('')
    }
  }

  const createVersion = async (payload: {
    name: string
    target_company: string
    target_title: string
    template_id: string
    selected_section_ids: string[]
    selected_entry_ids: string[]
    selected_material_ids: string[]
  }) => {
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/versions', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setCreatingVersion(false)
      setMessage('简历版本已创建')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '创建简历版本失败')
    }
  }

  const updateVersion = async (version: ResumeVersion, patch: Partial<ResumeVersion>) => {
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/versions/${version.id}`, {
        method: 'PUT',
        body: JSON.stringify({ ...version, ...patch }),
      })
      setMessage('简历版本已保存')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '保存简历版本失败')
    }
  }

  const duplicateVersion = async (version: ResumeVersion) => {
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/versions/duplicate', {
        method: 'POST',
        body: JSON.stringify({ version_id: version.id, name: `${version.name} 副本` }),
      })
      setMessage('简历版本已复制')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '复制简历版本失败')
    }
  }

  const deleteVersion = async (version: ResumeVersion) => {
    if (!window.confirm(`确定删除「${version.name}」吗？`)) return
    setError('')
    setMessage('')
    try {
      await requestJson(`/api/resume/versions/${version.id}`, { method: 'DELETE' })
      setMessage('简历版本已删除')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除简历版本失败')
    }
  }

  const useVersionAsCurrent = async (version: ResumeVersion) => {
    setUsingVersionId(version.id)
    setError('')
    setMessage('')
    try {
      await requestJson('/api/resume/use-version', {
        method: 'POST',
        body: JSON.stringify({ version_id: version.id }),
      })
      setMessage('已设为当前使用简历，后续评分、招呼语和投递会读取这个版本。')
      await loadCenter()
    } catch (error) {
      setError(error instanceof Error ? error.message : '设置当前简历失败')
    } finally {
      setUsingVersionId('')
    }
  }

  const exportVersionPdf = (version: ResumeVersion) => {
    const params = new URLSearchParams({
      version_id: version.id,
      template_id: version.template_id || '',
      show_photo: previewPhotoVisible ? '1' : '0',
    })
    window.location.href = `/api/resume/export-pdf?${params.toString()}`
  }

  const customSections = sections.filter(section => section.section_type === 'custom')

  if (loading) {
    return <div className="flex h-full items-center justify-center text-sm text-muted">加载简历中心...</div>
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-foreground">简历中心</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
            先把真实资料和经历沉淀在这里；后续可以按不同岗位选择内容，生成对应的简历版本。
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={loadCenter}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 rounded-[8px] border border-card-border bg-white p-1">
        {tabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-black transition-colors',
              activeTab === tab.id ? 'bg-[#FFF0E5] text-primary' : 'text-muted hover:bg-[#FFFCFA] hover:text-foreground'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <StatusMessage error={error} message={message} />
      <ImportPreviewDialog
        draft={importDraft}
        confirming={confirmingImport}
        onDraftChange={setImportDraft}
        onCancel={() => setImportDraft(null)}
        onConfirm={confirmImportOldResume}
      />
      <TemplateImportDialog
        draft={templateDraft}
        confirming={confirmingTemplate}
        onNameChange={name => setTemplateDraft(previous => previous ? { ...previous, name } : previous)}
        onBaseChange={base => setTemplateDraft(previous => previous ? {
          ...previous,
          base_template: base,
          layout: { ...previous.layout, base_template: base },
        } : previous)}
        onCancel={() => setTemplateDraft(null)}
        onConfirm={confirmImportUserTemplate}
      />

      {activeTab === 'profile' && (
        <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
          <aside className="space-y-4">
            <Card className="rounded-[8px] shadow-none">
              <CardHeader className="p-5">
                <CardTitle className="text-base font-black text-foreground">资料概览</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 p-5 pt-0 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted">姓名</span>
                  <span className="font-black text-foreground">{valueOf(profile.basics, 'name') || '未填写'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">教育背景</span>
                  <span className="font-black text-foreground">{education.length} 条</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">自定义格</span>
                  <span className="font-black text-foreground">{personalCustomFields.length} 个</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">经历板块</span>
                  <span className="font-black text-foreground">{sections.length} 个</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">简历版本</span>
                  <span className="font-black text-foreground">{versions.length} 个</span>
                </div>
              </CardContent>
            </Card>

            <PhotoPanel photo={photo} uploading={uploadingPhoto} onUpload={uploadPhoto} onDelete={deletePhoto} />

            <ImportOldResumeCard importing={importingResume} onImport={importOldResume} />

            <Card className="rounded-[8px] shadow-none">
              <CardHeader className="p-5">
                <CardTitle className="text-base font-black text-foreground">新增自定义模块</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 p-5 pt-0">
                <Input value={customTitle} onChange={event => setCustomTitle(event.target.value)} placeholder="例如：竞赛经历" />
                <Button type="button" className="w-full" onClick={addCustomSection} disabled={!customTitle.trim()}>
                  <Plus className="mr-2 h-4 w-4" />
                  新增模块
                </Button>
              </CardContent>
            </Card>
          </aside>

          <section className="space-y-5">
            <Card className="rounded-[8px] shadow-none">
              <CardHeader className="p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-base font-black text-foreground">个人信息</CardTitle>
                    <p className="mt-1 text-xs text-muted">这里只保存简历抬头常用的个人资料，教育和技能放在独立模块里维护。</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="ghost" onClick={resetResumeCenter} disabled={saving}>
                      <Trash2 className="mr-2 h-4 w-4" />
                      重置全部
                    </Button>
                    <Button type="button" onClick={saveProfile} disabled={saving}>
                      <Save className="mr-2 h-4 w-4" />
                      {saving ? '保存中...' : '保存资料'}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6 p-5 pt-0">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <Field label="姓名" value={valueOf(basics, 'name')} onChange={value => setBasicField('name', value)} />
                  <Field label="性别" value={valueOf(basics, 'gender')} onChange={value => setBasicField('gender', value)} />
                  <Field label="出生日期" value={valueOf(basics, 'birth_date')} onChange={value => setBasicField('birth_date', value)} placeholder="例如：2001.08" />
                  <Field label="籍贯" value={valueOf(basics, 'native_place')} onChange={value => setBasicField('native_place', value)} />
                  <Field label="电话" value={valueOf(contacts, 'phone')} onChange={value => setContactField('phone', value)} />
                  <Field label="邮箱" value={valueOf(contacts, 'email')} onChange={value => setContactField('email', value)} />
                  <Field label="政治面貌" value={valueOf(basics, 'political_status')} onChange={value => setBasicField('political_status', value)} />
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black text-foreground">自定义格</h3>
                    <Button type="button" size="sm" variant="secondary" onClick={() => setPersonalCustomFields(prev => [...prev, { label: '', value: '' }])}>
                      <Plus className="mr-2 h-3.5 w-3.5" />
                      新增
                    </Button>
                  </div>
                  {!personalCustomFields.length && <EmptyPanel>没有自定义格。</EmptyPanel>}
                  {personalCustomFields.map((item, index) => (
                    <div key={index} className="grid gap-3 rounded-[8px] border border-card-border bg-white p-3 md:grid-cols-[180px_1fr_auto]">
                      <Field label="字段名" value={item.label} onChange={value => updateCustomField(index, 'label', value)} placeholder="例如：民族" />
                      <Field label="内容" value={item.value} onChange={value => updateCustomField(index, 'value', value)} />
                      <div className="flex items-end">
                        <Button type="button" size="icon" variant="ghost" onClick={() => setPersonalCustomFields(prev => prev.filter((_, itemIndex) => itemIndex !== index))} title="删除自定义格">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                <EducationEditor education={education} onChange={setEducation} />
              </CardContent>
            </Card>

            {SECTION_KINDS.map(kind => (
              <SectionEditor
                key={kind.type}
                kind={kind}
                section={sectionByType.get(kind.type)}
                onCreate={createSection}
                onSaveSection={saveSection}
                onDeleteSection={deleteSection}
                onReload={loadCenter}
                setError={setError}
                setMessage={setMessage}
              />
            ))}

            {customSections.map(section => (
              <SectionEditor
                key={section.id}
                kind={{ type: 'custom', title: section.title, emptyText: '这个自定义模块还没有内容。', icon: Sparkles }}
                section={section}
                onCreate={createSection}
                onSaveSection={saveSection}
                onDeleteSection={deleteSection}
                onReload={loadCenter}
                setError={setError}
                setMessage={setMessage}
              />
            ))}
          </section>
        </div>
      )}

      {activeTab === 'versions' && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-black text-foreground">我的简历</h2>
              <p className="mt-1 text-sm text-muted">每个版本都会保存创建当时的资料快照。</p>
            </div>
            <Button type="button" onClick={() => setCreatingVersion(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建简历
            </Button>
          </div>

          {creatingVersion && (
            <VersionBuilder
              sections={sections}
              templates={templates}
              onCreate={createVersion}
              onCancel={() => setCreatingVersion(false)}
            />
          )}

          <div className="grid gap-5 xl:grid-cols-[minmax(420px,520px)_1fr]">
            <Card className="rounded-[8px] shadow-none">
              <CardHeader className="p-5">
                <CardTitle className="text-base font-black text-foreground">简历版本</CardTitle>
              </CardHeader>
              <CardContent className="p-5 pt-0">
                {!versions.length ? (
                  <EmptyPanel>还没有简历版本。点击“创建简历”后，可以选择资料和素材生成一个快照。</EmptyPanel>
                ) : (
                  <div className="space-y-3">
                    {versions.map(version => {
                      const isSelected = selectedVersion?.id === version.id
                      return (
                        <div
                          key={version.id}
                          className={cn(
                            'rounded-[8px] border bg-white p-4 transition-colors',
                            isSelected ? 'border-primary/70 bg-[#FFFCFA]' : 'border-card-border'
                          )}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <VersionNameEditor version={version} onSave={updateVersion} />
                          <div className="flex gap-2">
                            <Button type="button" size="sm" variant={isSelected ? 'default' : 'secondary'} onClick={() => setSelectedVersionId(version.id)}>
                              <Eye className="mr-2 h-3.5 w-3.5" />
                              预览
                            </Button>
                            <Button type="button" size="sm" variant="secondary" onClick={() => exportVersionPdf(version)}>
                              <Download className="mr-2 h-3.5 w-3.5" />
                              导出
                            </Button>
                            <Button type="button" size="sm" variant="secondary" onClick={() => useVersionAsCurrent(version)} disabled={usingVersionId === version.id}>
                              <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                              {usingVersionId === version.id ? '设置中' : '设为当前'}
                            </Button>
                            <Button type="button" size="sm" variant="secondary" onClick={() => duplicateVersion(version)}>
                              <Copy className="mr-2 h-3.5 w-3.5" />
                              复制
                              </Button>
                              <Button type="button" size="icon" variant="ghost" onClick={() => deleteVersion(version)} title="删除版本">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
                            <div>
                              <div className="text-xs font-black text-muted">目标公司</div>
                              <div className="mt-1 text-foreground">{version.target_company || '未填写'}</div>
                            </div>
                            <div>
                              <div className="text-xs font-black text-muted">目标职位</div>
                              <div className="mt-1 text-foreground">{version.target_title || '未填写'}</div>
                            </div>
                            <div>
                              <div className="text-xs font-black text-muted">模板</div>
                              <div className="mt-1 text-foreground">{templateDisplayLabel(version.template_id, templates)}</div>
                            </div>
                            <div>
                              <div className="text-xs font-black text-muted">已选内容</div>
                              <div className="mt-1 text-foreground">
                                {version.selected_section_ids?.length || 0} 板块 · {version.selected_entry_ids?.length || 0} 经历 · {version.selected_material_ids?.length || 0} 素材
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <ResumePreview
              version={selectedVersion}
              templates={templates}
              photo={photo}
              showPhoto={previewPhotoVisible}
              onShowPhotoChange={setPreviewPhotoVisible}
              onTemplateChange={(version, templateId) => updateVersion(version, { template_id: templateId })}
            />
          </div>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
          <TemplateImportCard importing={importingTemplate} onImport={importUserTemplate} />
          <Card className="rounded-[8px] shadow-none">
            <CardHeader className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base font-black text-foreground">模板中心</CardTitle>
                  <p className="mt-1 text-xs text-muted">通过 A4 缩略图查看模板版式，选择时更接近最终简历效果。</p>
                </div>
                <div className="text-xs font-black text-primary">{templates.length} 个模板</div>
              </div>
            </CardHeader>
            <CardContent className="space-y-7 p-5 pt-0">
              <section className="space-y-3">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <div className="text-sm font-black text-foreground">BossHunter 当前模板</div>
                    <div className="mt-1 text-xs text-muted">这些模板已接入当前简历生成与导出流程。</div>
                  </div>
                </div>
              <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
                {templates.map(template => (
                  <TemplateGalleryCard
                    key={template.id}
                    template={template}
                    templates={templates}
                    deleting={deletingTemplateId === template.id}
                    onDelete={templateToDelete => void deleteUserTemplate(templateToDelete)}
                  />
                ))}
              </div>
              </section>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
