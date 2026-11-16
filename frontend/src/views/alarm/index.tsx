import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/alarm'
const columns = [
  "规则编号",
  "监控指标",
  "告警条件",
  "告警级别",
  "通知渠道",
  "静默周期",
  "升级策略",
  "规则状态"
]
const actions = [
  "启用告警",
  "暂停告警",
  "关闭告警"
]
const statuses = [
  "草稿",
  "已启用",
  "已暂停",
  "已关闭"
]
const stats = [
  {
    "label": "告警规则总数",
    "value": 0
  },
  {
    "label": "已启用告警",
    "value": 0
  },
  {
    "label": "已暂停告警",
    "value": 0
  }
]

type Row = Record<string, string | number | null>

export default function AlarmView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [noticeMessage, setNoticeMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [versionCode, setVersionCode] = useState('')
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('告警规则列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '流告警规则列表读取失败')
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
      if (!response.ok) {
        throw new Error('流告警规则动作未生效，请稍后重试')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '流告警规则操作失败')
    }
  }

  async function consumeWindowVersion(row: Row) {
    setErrorMessage('')
    setNoticeMessage('')
    if (!versionCode.trim()) {
      setErrorMessage('请先填写要消费的窗口配置版本编号')
      return
    }
    try {
      const response = await request(`${ENDPOINT}/${row.id}/consume`, {
        method: 'POST',
        body: JSON.stringify({ 版本编号: versionCode.trim() }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message ?? '窗口配置版本数据消费失败')
      }
      setNoticeMessage(payload.message ?? '窗口配置版本数据已消费')
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '窗口配置版本数据消费失败')
    }
  }

  return (
    <section className="page" data-module="alarm">
      <header className="page-head">
        <div>
          <h2>流告警规则管理</h2>
          <p className="page-desc">维护流告警的监控指标、触发条件与通知策略，为流告警规则管理提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('告警规则登记入口尚未接入审批流')}>
            登记告警规则
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出流告警规则清单
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
        <label className="filter-item">
          <span>窗口配置版本编号</span>
          <input
            value={versionCode}
            placeholder="如 WIND-0002-v1"
            onChange={(event) => setVersionCode(event.target.value)}
          />
        </label>
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
                <button className="link" type="button" onClick={() => void consumeWindowVersion(row)}>
                  消费窗口配置
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无流告警规则数据，可先登记告警规则</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条流告警规则记录</span>
        {noticeMessage && <span className="notice-text">{noticeMessage}</span>}
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
