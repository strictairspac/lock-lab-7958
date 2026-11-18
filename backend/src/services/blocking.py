"""阻塞链证据采集：B 等待行锁期间，由独立第三连接采样 pg_blocking_pids 并分段落库。

口径与边界：
- 段（segment）：阻塞者集合不变的一段连续确认时间；开启即提交，等待中证据页即可查到已确认段。
- 换阻塞者分段：阻塞者身份 = (pid, backend_start)，连接复用后 backend_start 变化即视为新阻塞者，换段记录。
- 空档（gap）：采集中断（连接断开/采集器重启）恢复时，距上次确认超过阈值则补一条 kind='gap' 标记，空档内阻塞关系未确认；已确认的段不受影响、照常可查。
- 幂等：(trial_id, waiter_pid, seg_no) 唯一，重试写入被 ON CONFLICT DO NOTHING 吸收，不会重复记同一段。
- 不延长持锁：采集在独立线程、独立连接上进行，只读共享内存视图；A 的提交只等待 B 结束事件，不等待采集器。
"""
import threading,time
from datetime import datetime,timezone
from sqlalchemy import text,select,func,update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.config.database import engine,Session
from src.models.entities import BlockEvidence
from src.utils.serialization import record

INTERVAL=0.025   # 采样间隔（秒），小于最小锁等待上限 50ms
FLUSH=0.1        # 段内 last_seen/samples 节流落库间隔
GAP_AFTER=INTERVAL*3  # 距上次确认超过该时长，恢复时标记空档

INFO_SQL=text("""SELECT pid,usename,application_name,state,wait_event_type,wait_event,
backend_start,xact_start,left(query,160) AS query
FROM pg_stat_activity WHERE pid = ANY(pg_blocking_pids(:pid)) ORDER BY pid""")

def _now(): return datetime.now(timezone.utc)
def _key(rows): return tuple((r.pid,r.backend_start.isoformat() if r.backend_start else '') for r in rows)
def _info(rows):
    return [{'pid':r.pid,'user':r.usename,'app':r.application_name,'state':r.state,
             'wait':((r.wait_event_type or '')+'/'+(r.wait_event or '')).strip('/'),
             'backend_start':r.backend_start.isoformat() if r.backend_start else None,
             'xact_start':r.xact_start.isoformat() if r.xact_start else None,
             'query':r.query} for r in rows]

class BlockCollector:
    """单场演练的阻塞采样器。set_waiter 提供 B 的 backend PID 后开始生效；run 在独立线程运行。"""
    def __init__(self,trial_id,interval=INTERVAL):
        self.trial_id=trial_id;self.interval=interval
        self.ready=threading.Event();self.pid=None
        self.segments=0;self.gaps=0;self.error=''
    def set_waiter(self,pid): self.pid=pid;self.ready.set()
    def run(self,stop):
        if not self.ready.wait(5): return
        try: self._loop(stop)
        except Exception as e: self.error=str(e)

    # ---- 落库：每次独立提交，已确认记录中断后仍可查 ----
    def _next_seg(self,db):
        return db.scalar(select(func.coalesce(func.max(BlockEvidence.seg_no),0)).where(
            BlockEvidence.trial_id==self.trial_id,BlockEvidence.waiter_pid==self.pid))+1
    def _append(self,kind,blockers,first,last,samples,note=''):
        stmt=pg_insert(BlockEvidence).values(trial_id=self.trial_id,waiter_pid=self.pid,kind=kind,
            blockers=blockers,first_seen=first,last_seen=last,samples=samples,note=note)
        for _ in range(3):
            with Session() as db:
                seg=self._next_seg(db)
                ident=db.execute(stmt.values(seg_no=seg).on_conflict_do_nothing().returning(BlockEvidence.id)).scalar()
                db.commit()
                if ident: return ident
        raise RuntimeError('阻塞证据段序号竞争未决')
    def _touch(self,ident,last,samples):
        with Session() as db:
            db.execute(update(BlockEvidence).where(BlockEvidence.id==ident).values(last_seen=last,samples=samples))
            db.commit()
    def _resume(self):
        now=_now()
        with Session() as db:
            last=db.scalar(select(BlockEvidence).where(BlockEvidence.trial_id==self.trial_id,
                BlockEvidence.waiter_pid==self.pid).order_by(BlockEvidence.seg_no.desc()).limit(1))
        if last and (now-last.last_seen).total_seconds()>GAP_AFTER:
            self._append('gap',[],last.last_seen,now,0,'采集中断后恢复：空档内阻塞关系未确认')
            self.gaps+=1

    def _loop(self,stop):
        conn=None;cur=None  # cur={'id','key','samples','seen','flushed'}
        def close():
            nonlocal cur
            if cur:
                try: self._touch(cur['id'],cur['seen'],cur['samples'])
                except Exception: pass
                cur=None
        while not stop.is_set():
            now=_now()
            try:
                if conn is None:
                    conn=engine.connect()
                    self._resume()   # 中断恢复：先标空档，再续采
                rows=conn.execute(INFO_SQL,{'pid':self.pid}).all()
                key=_key(rows)
                if cur and key==cur['key']:
                    cur['samples']+=1;cur['seen']=now
                    if now.timestamp()-cur['flushed']>=FLUSH:
                        self._touch(cur['id'],now,cur['samples']);cur['flushed']=now.timestamp()
                else:
                    close()
                    if key:
                        ident=self._append('segment',_info(rows),now,now,1)
                        self.segments+=1
                        cur={'id':ident,'key':key,'samples':1,'seen':now,'flushed':now.timestamp()}
            except Exception:
                close()
                try: conn.close()
                except Exception: pass
                conn=None
            time.sleep(self.interval)
        close()
        if conn is not None: conn.close()

def timeline(db,trial_id):
    """按段序号返回该演练全部阻塞证据（含空档标记），等待中即可查询已确认部分。"""
    rows=db.scalars(select(BlockEvidence).where(BlockEvidence.trial_id==trial_id).order_by(BlockEvidence.seg_no)).all()
    return [record(r) for r in rows]
