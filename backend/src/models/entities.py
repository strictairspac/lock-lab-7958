from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, UniqueConstraint
from datetime import datetime, timezone
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(120),unique=True,nullable=False)
    password=Column(String(300),nullable=False);role=Column(String(20),nullable=False)
class Sample(Base):
    __tablename__='samples'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    title=Column(String(160),nullable=False);quantity=Column(Integer,nullable=False);location=Column(String(120),nullable=False)
class Transfer(Base):
    __tablename__='transfers'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    sample_id=Column(Integer,ForeignKey('samples.id'),nullable=False);destination=Column(String(120),nullable=False)
    quantity=Column(Integer,nullable=False);note=Column(String(300),default='')
class Trial(Base):
    __tablename__='trials'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False)
    transfer_id=Column(Integer,ForeignKey('transfers.id'),nullable=False);timeout_ms=Column(Integer,nullable=False)
    status=Column(String(20),default='queued',nullable=False);result=Column(JSON,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc));error=Column(Text,default='')
class TrialBalance(Base):
    __tablename__='trial_balances'
    trial_id=Column(Integer,ForeignKey('trials.id'),primary_key=True);remaining=Column(Integer,nullable=False);received=Column(Integer,nullable=False,default=0)
class Receipt(Base):
    __tablename__='receipts'
    id=Column(Integer,primary_key=True);trial_id=Column(Integer,ForeignKey('trials.id'),nullable=False)
    actor=Column(String(20),nullable=False);quantity=Column(Integer,nullable=False)
    __table_args__=(UniqueConstraint('trial_id','actor'),)
class BlockEvidence(Base):
    __tablename__='block_evidences'
    id=Column(Integer,primary_key=True);trial_id=Column(Integer,ForeignKey('trials.id'),nullable=False)
    waiter_pid=Column(Integer,nullable=False);seg_no=Column(Integer,nullable=False)
    kind=Column(String(10),nullable=False,default='segment')
    blockers=Column(JSON,nullable=False,default=list)
    first_seen=Column(DateTime(timezone=True),nullable=False);last_seen=Column(DateTime(timezone=True),nullable=False)
    samples=Column(Integer,nullable=False,default=1);note=Column(String(200),default='')
    __table_args__=(UniqueConstraint('trial_id','waiter_pid','seg_no'),)
class Audit(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True);actor=Column(String(120),nullable=False);action=Column(String(160),nullable=False)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
