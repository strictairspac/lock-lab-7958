import {table} from '../components/common/table.js';
import {badge} from '../components/common/badge.js';
import {esc,date} from '../utils/html.js';
const ms=v=>{const d=new Date(v);return d.toLocaleTimeString('zh-CN',{hour12:false})+'.'+String(d.getMilliseconds()).padStart(3,'0')};
const dur=(a,b)=>Math.max(0,Math.round(new Date(b)-new Date(a)))+' ms';
function blockingSection(blocking,hasResult){
  if(!blocking)return '';
  const segs=blocking.segments||[];
  if(!segs.length)return hasResult?'<div class="notice">该演练无阻塞采样段（采集功能上线前执行，或 B 等待期间未被阻塞）。</div>':'';
  const waiter=segs[0].waiter_pid;
  const rows=segs.map(s=>{
    if(s.kind==='gap')return [`#${s.seg_no}`,'<span class="badge">空档</span>',`<em>${esc(s.note||'采集中断，空档内阻塞关系未确认')}</em>`,ms(s.first_seen),dur(s.first_seen,s.last_seen),'—'];
    const who=(s.blockers||[]).map(b=>`<strong>PID ${b.pid}</strong> · ${esc(b.user)} · ${esc(b.state||'')}${b.wait?` · ${esc(b.wait)}`:''}${b.backend_start?`<small>会话起始 ${esc(b.backend_start)}</small>`:''}${b.query?`<small>${esc(b.query)}</small>`:''}`).join('<br>');
    return [`#${s.seg_no}`,'<span class="badge">阻塞段</span>',who,ms(s.first_seen),dur(s.first_seen,s.last_seen),s.samples];
  });
  return `<div class="section-top"><h2>阻塞时间线</h2><span>等待事务 B · PID ${waiter} · 25MS 采样 · 换阻塞者分段</span></div>${table(['段','类型','阻塞者（Backend PID · 用户 · 状态）','首见','持续','采样'],rows)}`;
}
export function evidencePage(trial,blocking){
  if(!trial)return '<div class="empty">尚无冲突证据。请到「并发执行」发起演练，完成后在此复核事务回滚结果。</div>';
  const r=trial.result;
  return `<div class="evidence-top"><div><span class="eyebrow">EVIDENCE / #${trial.id}</span><h2>${esc(trial.name)} ${badge(trial.status)}</h2><p>${date(trial.created_at)} · PostgreSQL 真实双连接</p></div><button id="export" data-id="${trial.id}">导出 JSON ↓</button></div>${trial.error?`<div class="error">${esc(trial.error)}。请检查配置后重新发起演练。</div>`:''}${blockingSection(blocking,!!r)}${r?`<div class="verdict"><div class="verdict-icon">${r.invariant_passed?'✓':'!'}</div><div><span class="eyebrow">CONSERVATION CHECK</span><h2>${r.invariant_passed?'回滚完整，数量守恒':'不变量检查未通过'}</h2><p>${r.initial} 份 = 剩余 ${r.remaining} 份 + 已接收 ${r.received} 份 · 提交回执 ${r.receipt_count} 条</p></div><div class="equation">${r.remaining}<span> + </span>${r.received}<span> = </span>${r.initial}</div></div><div class="section-top"><h2>数据库事务轨迹</h2><span>证据来自实际连接与错误码</span></div>${table(['连接','Backend PID','事务事件','等待 / SQLSTATE'],r.traces.map(t=>[`<strong>事务 ${esc(t.actor)}</strong>`,t.pid,esc(t.event),t.sqlstate?`${t.wait_ms} ms / ${esc(t.sqlstate)}`:(t.event==='row_lock_acquired'?'已获取行锁':'提交成功')]))}<div class="evidence-notes"><section><h3>判定口径</h3><p>${esc(r.formula)}</p><p>B 事务先插入的回执，已随 lock_timeout 事务回滚。A 持锁等待由线程事件协调，未伪造等待结果。</p></section><section><h3>复现摘要</h3><p>${esc(r.mode)}</p><code>${esc(r.checksum)}</code></section></div>`:'<div class="notice">任务正在后台执行，页面每 1.5 秒刷新。可以保留此页或稍后从运行列表返回。</div>'}`;
}
