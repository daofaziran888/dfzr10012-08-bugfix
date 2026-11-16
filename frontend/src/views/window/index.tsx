import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/window'
const columns = [
  "窗口编号",
  "数据流名称",
  "窗口类型",
  "窗口长度",
  "滑动步长",
  "延迟容忍",
  "触发策略",
  "窗口状态"
]
const actions = [
  "启用窗口",
  "暂停窗口",
  "关闭窗口"
]
const statuses = [
  "草稿",
  "生效中",
  "已暂停",
  "已关闭"
]
const stats = [
  {
    "label": "窗口定义总数",
    "value": 0
  },
  {
    "label": "生效中窗口",
    "value": 0
  },
  {
    "label": "已暂停窗口",
    "value": 0
  }
]
const versionColumns = ["版本编号", "窗口类型", "延迟容忍", "暂停标记", "触发策略", "窗口状态", "来源"]
const importFields = ["窗口编号", "版本号", "数据流名称", "窗口类型", "窗口长度", "滑动步长", "延迟容忍", "触发策略"]

type Row = Record<string, string | number | boolean | null>

const emptyImportForm: Record<string, string> = {
  窗口编号: '',
  版本号: 'v1',
  数据流名称: '',
  窗口类型: '',
  窗口长度: '',
  滑动步长: '',
  延迟容忍: '',
  触发策略: '',
  暂停标记: 'false',
}

export default function WindowView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [noticeMessage, setNoticeMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const filterFields = useMemo(() => columns.slice(0, 3), [])
  const [importOpen, setImportOpen] = useState(false)
  const [importForm, setImportForm] = useState<Record<string, string>>(emptyImportForm)
  const [packageText, setPackageText] = useState('')
  const [detail, setDetail] = useState<{ windowCode: string; versions: Row[]; triggers: Row[] } | null>(null)

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('窗口定义列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '窗口计算配置列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    setNoticeMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message ?? '窗口计算配置动作未生效，请稍后重试')
      }
      setNoticeMessage(payload.message ?? `窗口定义已${action}`)
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '窗口计算配置操作失败')
    }
  }

  async function runTrigger(row: Row) {
    setErrorMessage('')
    setNoticeMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/trigger`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message ?? '窗口触发未生效，请稍后重试')
      }
      setNoticeMessage(payload.message ?? '窗口已触发')
      if (detail) {
        await openDetail(row)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '窗口触发操作失败')
    }
  }

  async function openDetail(row: Row) {
    setErrorMessage('')
    setNoticeMessage('')
    const windowCode = String(row['窗口编号'] ?? '')
    try {
      const [versionResp, triggerResp] = await Promise.all([
        request(`${ENDPOINT}/versions?window_code=${encodeURIComponent(windowCode)}`),
        request(`${ENDPOINT}/triggers?window_code=${encodeURIComponent(windowCode)}`),
      ])
      if (!versionResp.ok || !triggerResp.ok) {
        throw new Error('窗口配置版本数据读取失败')
      }
      const versions = await versionResp.json()
      const triggers = await triggerResp.json()
      setDetail({ windowCode, versions: versions.items ?? [], triggers: triggers.items ?? [] })
    } catch (error) {
      setDetail(null)
      setErrorMessage(error instanceof Error ? error.message : '窗口配置版本数据读取失败')
    }
  }

  async function submitImport() {
    setErrorMessage('')
    setNoticeMessage('')
    let values: Record<string, unknown>
    const text = packageText.trim()
    if (text) {
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>
        values = typeof parsed === 'object' && parsed !== null && 'items' in parsed ? parsed : { items: [parsed] }
      } catch {
        setErrorMessage('配置包 JSON 无法解析，请检查文件内容')
        return
      }
    } else {
      values = { ...importForm, 暂停标记: importForm.暂停标记 === 'true' }
    }
    try {
      const response = await request(`${ENDPOINT}/import`, {
        method: 'POST',
        body: JSON.stringify({ values }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message ?? '窗口配置包导入失败')
      }
      setNoticeMessage(payload.message ?? '窗口配置包已导入')
      setImportOpen(false)
      setImportForm(emptyImportForm)
      setPackageText('')
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '窗口配置包导入失败')
    }
  }

  return (
    <section className="page" data-module="window">
      <header className="page-head">
        <div>
          <h2>窗口计算配置管理</h2>
          <p className="page-desc">维护窗口计算的类型选择、长度配置与触发策略，为窗口计算配置提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setImportOpen(true)}>
            导入窗口配置包
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出窗口计算配置清单
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/versions/file`, '_blank')}>
            下载窗口配置版本文件
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td className="row-actions">
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
                <button className="link" type="button" onClick={() => void runTrigger(row)}>
                  触发窗口
                </button>
                <button className="link" type="button" onClick={() => void openDetail(row)}>
                  详情
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无窗口计算配置数据，可先导入窗口配置包</td>
            </tr>
          )}
        </tbody>
      </table>

      {detail && (
        <section className="detail-panel">
          <h3>窗口配置版本数据：{detail.windowCode}</h3>
          <table className="data-table">
            <thead>
              <tr>
                {versionColumns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {detail.versions.map((version) => (
                <tr key={String(version['版本编号'])}>
                  {versionColumns.map((column) => (
                    <td key={column}>
                      {column === '暂停标记' ? (version[column] ? '已暂停' : '运行中') : (version[column] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
              {detail.versions.length === 0 && (
                <tr>
                  <td className="empty-state" colSpan={versionColumns.length}>暂无窗口配置版本数据，可通过导入配置包写入</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="page-desc">窗口触发结果共 {detail.triggers.length} 条；暂停期间不生成新的窗口触发结果。</p>
        </section>
      )}

      {importOpen && (
        <div className="modal-mask" onClick={() => setImportOpen(false)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h3>导入窗口配置包</h3>
            <div className="modal-form">
              {importFields.map((field) => (
                <label key={field} className="filter-item">
                  <span>{field}</span>
                  <input
                    value={importForm[field] ?? ''}
                    placeholder={`填写${field}`}
                    onChange={(event) => setImportForm((prev) => ({ ...prev, [field]: event.target.value }))}
                  />
                </label>
              ))}
              <label className="filter-item">
                <span>暂停标记</span>
                <select
                  value={importForm.暂停标记}
                  onChange={(event) => setImportForm((prev) => ({ ...prev, 暂停标记: event.target.value }))}
                >
                  <option value="false">运行</option>
                  <option value="true">暂停</option>
                </select>
              </label>
              <label className="filter-item">
                <span>配置包 JSON（可选，粘贴下载的版本文件内容）</span>
                <textarea
                  rows={4}
                  value={packageText}
                  placeholder='{"items": [{"窗口编号": "WIND-0002", "版本号": "v1", "暂停标记": true, "延迟容忍": "10s", "窗口类型": "滑动窗口"}]}'
                  onChange={(event) => setPackageText(event.target.value)}
                />
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn primary" type="button" onClick={() => void submitImport()}>确认导入</button>
              <button className="btn ghost" type="button" onClick={() => setImportOpen(false)}>取消</button>
            </div>
            {errorMessage && <p className="error-text">{errorMessage}</p>}
          </div>
        </div>
      )}

      <footer className="page-foot">
        <span>共 {total} 条窗口计算配置记录</span>
        {noticeMessage && <span className="notice-text">{noticeMessage}</span>}
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
