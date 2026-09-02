import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class ProcurementPortal(Base):
    __tablename__ = "procurement_portals"

    portal_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    country = Column(String(10), nullable=False)
    portal_type = Column(String(20), nullable=False)
    base_url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    last_crawled_at = Column(DateTime, nullable=True)

    opportunities = relationship("RFPOpportunity", back_populates="portal")

class RFPOpportunity(Base):
    __tablename__ = "rfp_opportunities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    portal_id = Column(String(50), ForeignKey("procurement_portals.portal_id"))
    external_rfp_id = Column(String(100))
    title = Column(Text, nullable=False)
    issuing_org = Column(String(255))
    country = Column(String(10))
    opportunity_type = Column(String(50), default="RFP")
    source_url = Column(Text, nullable=False)
    publication_date = Column(String(20))
    submission_deadline = Column(String(20))
    estimated_value_usd = Column(Float, default=0.0)
    raw_content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    portal = relationship("ProcurementPortal", back_populates="opportunities")
    evaluation = relationship("RFPExecutionEvaluation", back_populates="rfp", uselist=False, cascade="all, delete-orphan")

class RFPExecutionEvaluation(Base):
    __tablename__ = "rfp_ai_evaluations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rfp_id = Column(String(36), ForeignKey("rfp_opportunities.id"))
    relevance_score = Column(Integer)
    is_relevant = Column(Boolean, nullable=False)
    why_relevant = Column(Text)
    eai_deliverables = Column(JSON)
    missing_requirements = Column(JSON)
    ai_summary = Column(Text)
    recommendation = Column(String(20))
    evaluated_at = Column(DateTime, default=datetime.utcnow)

    rfp = relationship("RFPOpportunity", back_populates="evaluation")

class EAIKnowledgeChunk(Base):
    __tablename__ = "eai_knowledge_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_domain = Column(String(100))
    category = Column(String(50))
    title = Column(String(255))
    content = Column(Text, nullable=False)
